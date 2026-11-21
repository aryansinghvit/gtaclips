"""Autonomous Multi-Channel YouTube Shorts Scheduler & Unique Metadata Engine.

Features:
1. Multi-Channel YouTube Routing:
   - 'ghost_clips' (English): IShowSpeed, MrBeast, Kai Cenat, English creators.
   - 'gta6_clips' (Hindi): Techno Gamerz, CarryMinati, Total Gaming, Hindi creators.
   - Independent OAuth tokens, publishing queues, and 6-slot calendars per channel.
2. Unique Per-Clip Metadata:
   - Dynamic titles with #Shorts.
   - Unique scene synopsis from transcript dialogue and visual action.
   - Dialogue quotes, rotating CTAs, channel prompts, and tailored tags.
3. 6 Slots/Day Schedule (12PM, 6PM, 9PM, 12AM, 6AM, 9AM).
4. Immediate local MP4 deletion after upload.
"""

import datetime
import gc
import json
import os
import re
import sys
import time
from pathlib import Path

# Required Google libraries
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
CONFIG_DIR = Path.home() / "BeyondGTAClips" / "youtube_config"
CHANNELS_FILE = CONFIG_DIR / "channels.json"

DEFAULT_CHANNELS_DATA = {
    "default_channel": "ghost_clips",
    "channels": {
        "ghost_clips": {
            "id": "ghost_clips",
            "display_name": "Ghost Clips",
            "aliases": ["ghost clips", "ghost", "ghostclips", "english", "speed", "mrbeast"],
            "language": "en",
            "creators": ["ishowspeed", "speed", "mrbeast", "kai cenat", "xqc", "adin ross"],
            "folder": "ghost_clips",
        },
        "gta6_clips": {
            "id": "gta6_clips",
            "display_name": "GTA 6 Clips",
            "aliases": ["gta 6 clips", "gta6 clips", "gta 6", "gta6", "hindi", "techno", "carry"],
            "language": "hi",
            "creators": ["techno gamerz", "technogamerz", "carryminati", "carry", "total gaming", "mythpat"],
            "folder": "gta6_clips",
        },
    },
}


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_channels():
    ensure_config_dir()
    if CHANNELS_FILE.exists():
        try:
            return json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    CHANNELS_FILE.write_text(json.dumps(DEFAULT_CHANNELS_DATA, indent=2), encoding="utf-8")
    return DEFAULT_CHANNELS_DATA


def resolve_channel(channel_input=None):
    """Resolves channel name/alias or defaults to ghost_clips."""
    data = load_channels()
    channels = data.get("channels", {})
    if not channel_input:
        default_key = data.get("default_channel", "ghost_clips")
        return channels.get(default_key, list(channels.values())[0])

    clean_in = str(channel_input).strip().lower()
    for ch_key, ch_info in channels.items():
        if clean_in == ch_key.lower() or clean_in == ch_info.get("display_name", "").lower():
            return ch_info
        for alias in ch_info.get("aliases", []):
            if clean_in == alias.lower() or alias.lower() in clean_in:
                return ch_info

    # Creator-based detection fallback
    for ch_key, ch_info in channels.items():
        for cr in ch_info.get("creators", []):
            if cr in clean_in:
                return ch_info

    default_key = data.get("default_channel", "ghost_clips")
    return channels.get(default_key, list(channels.values())[0])


def get_channel_dir(channel_profile):
    ch_id = channel_profile.get("id") or channel_profile.get("folder") or "ghost_clips"
    ch_dir = CONFIG_DIR / ch_id
    ch_dir.mkdir(parents=True, exist_ok=True)
    return ch_dir


def get_client_secrets_file(channel_profile):
    ch_dir = get_channel_dir(channel_profile)
    f = ch_dir / "client_secrets.json"
    if f.exists():
        return f
    root_f = CONFIG_DIR / "client_secrets.json"
    if root_f.exists():
        return root_f
    return f


def get_token_file(channel_profile):
    ch_dir = get_channel_dir(channel_profile)
    f = ch_dir / "token.json"
    if f.exists():
        return f
    if channel_profile.get("id") == "ghost_clips":
        root_f = CONFIG_DIR / "token.json"
        if root_f.exists():
            return root_f
    return f


def get_queue_file(channel_profile):
    ch_dir = get_channel_dir(channel_profile)
    f = ch_dir / "scheduled_queue.json"
    if f.exists():
        return f
    if channel_profile.get("id") == "ghost_clips":
        root_f = CONFIG_DIR / "scheduled_queue.json"
        if root_f.exists():
            return root_f
    return f


def get_authenticated_service(channel=None):
    """Authenticates using stored token.json for the specified channel."""
    ensure_config_dir()
    ch_profile = resolve_channel(channel)
    token_file = get_token_file(ch_profile)
    client_secrets_file = get_client_secrets_file(ch_profile)
    ch_name = ch_profile.get("display_name", "Ghost Clips")

    creds = None
    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        except Exception as exc:
            print(f"[warning] Failed to load {token_file}: {exc}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                token_file.write_text(creds.to_json(), encoding="utf-8")
            except Exception as exc:
                print(f"[warning] Refreshing token failed for {ch_name}: {exc}")
                creds = None

        if not creds:
            if not client_secrets_file.exists():
                print(f"\n[MISSING] client_secrets.json not found in:\n  {client_secrets_file}")
                print("\nPlease place your Google Cloud OAuth client_secrets.json there and run:")
                print(f"  py -3.13 beyondgtaclips.py youtube-auth --channel \"{ch_name}\"\n")
                sys.exit(1)

            print(f"\n[auth] Authorizing YouTube channel: {ch_name} ({ch_profile.get('language', 'en').upper()})", flush=True)
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_file), SCOPES)
            message = (
                f"\n=======================================================\n"
                f"PLEASE OPEN THIS URL IN YOUR BROWSER TO AUTHORIZE '{ch_name}':\n"
                f"{{url}}\n"
                f"=======================================================\n"
            )
            print(f"[auth] Starting local auth server on port 8080...", flush=True)
            try:
                creds = flow.run_local_server(
                    port=8080,
                    prompt="consent",
                    access_type="offline",
                    authorization_prompt_message=message,
                    open_browser=True,
                )
            except OSError as err:
                print(f"[warning] Port 8080 busy ({err}), falling back to automatic port...", flush=True)
                creds = flow.run_local_server(
                    port=0,
                    prompt="consent",
                    access_type="offline",
                    authorization_prompt_message=message,
                    open_browser=True,
                )
            token_file.write_text(creds.to_json(), encoding="utf-8")
            print(f"[ok] YouTube credentials for '{ch_name}' saved to {token_file}", flush=True)

    return build("youtube", "v3", credentials=creds)


def load_queue_log(channel=None):
    ch_profile = resolve_channel(channel)
    q_file = get_queue_file(ch_profile)
    if q_file.exists():
        try:
            return json.loads(q_file.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_queue_log(queue, channel=None):
    ch_profile = resolve_channel(channel)
    q_file = get_queue_file(ch_profile)
    q_file.parent.mkdir(parents=True, exist_ok=True)
    q_file.write_text(json.dumps(queue, indent=2, default=str), encoding="utf-8")


# 6 slots per day starting at 12:00 PM local time:
# Slot 1: 12:00 PM (+0h)
# Slot 2: 06:00 PM (+6h)
# Slot 3: 09:00 PM (+9h)
# Slot 4: 12:00 AM Midnight (+12h)
# Slot 5: 06:00 AM (+18h)
# Slot 6: 09:00 AM (+21h)
DAILY_OFFSETS_HOURS = [0, 6, 9, 12, 18, 21]


def calculate_next_slots(count, channel=None, interval_hours=3, first_immediate=True):
    """Calculates strictly 6 slots per day for the specified channel.
    If the channel queue has no active future clips, the 1st clip is set to None (Immediate / Public).
    Remaining clips are scheduled into the 6 standard daily slots:
    12:00 PM, 06:00 PM, 09:00 PM, 12:00 AM, 06:00 AM, 09:00 AM.
    """
    queue = load_queue_log(channel=channel)
    local_now = datetime.datetime.now().astimezone()

    latest_dt = None
    for item in queue:
        try:
            pub_str = item.get("publish_at", "")
            if pub_str and pub_str != "IMMEDIATE":
                dt = datetime.datetime.fromisoformat(pub_str.replace("Z", "+00:00")).astimezone()
                if latest_dt is None or dt > latest_dt:
                    latest_dt = dt
        except Exception:
            pass

    slots = []
    # If the queue has future scheduled clips, continue seamlessly from the end of the queue
    if latest_dt and latest_dt > local_now + datetime.timedelta(minutes=10) and len(queue) > 0:
        already_scheduled = len(queue)
        first_item = queue[0]
        first_pub = first_item.get("publish_at", "")
        if first_pub and first_pub != "IMMEDIATE":
            try:
                first_dt = datetime.datetime.fromisoformat(first_pub.replace("Z", "+00:00")).astimezone()
                base_date = first_dt.date()
            except Exception:
                base_date = local_now.date()
        else:
            base_date = local_now.date()

        for i in range(count):
            idx = already_scheduled + i
            day_index = idx // 6
            slot_in_day = idx % 6
            target_date = base_date + datetime.timedelta(days=day_index)
            base_12pm = datetime.datetime(target_date.year, target_date.month, target_date.day, 12, 0, 0).astimezone()
            slot_dt = base_12pm + datetime.timedelta(hours=DAILY_OFFSETS_HOURS[slot_in_day])
            slots.append(slot_dt.astimezone(datetime.timezone.utc))
    else:
        # Starting fresh or previous queue already completed
        curr_date = local_now.date()
        base_12pm = datetime.datetime(curr_date.year, curr_date.month, curr_date.day, 12, 0, 0).astimezone()
        candidate_slots = []
        for day_offset in range(60):
            day_base = base_12pm + datetime.timedelta(days=day_offset)
            for s_offset in DAILY_OFFSETS_HOURS:
                candidate = day_base + datetime.timedelta(hours=s_offset)
                if candidate > local_now + datetime.timedelta(minutes=15):
                    candidate_slots.append(candidate.astimezone(datetime.timezone.utc))
                    if len(candidate_slots) >= count + (1 if first_immediate else 0):
                        break
            if len(candidate_slots) >= count + (1 if first_immediate else 0):
                break

        if first_immediate:
            # Slot 1 is None -> Upload immediately as PUBLIC!
            slots = [None] + candidate_slots[:count - 1]
        else:
            slots = candidate_slots[:count]

    return slots


def format_rich_metadata(clip_info: dict, channel_profile: dict, mp4_name: str = ""):
    """Formats unique, viral Title, Description and Tags per clip."""
    creator = clip_info.get("creator") or "BeyondGTAClips"
    lang = channel_profile.get("language", "en")
    ch_name = channel_profile.get("display_name", "Ghost Clips")

    # 1. UNIQUE VIRAL TITLE
    raw_hook = (clip_info.get("hook") or clip_info.get("title") or mp4_name).replace("*", "").strip()
    if "#shorts" not in raw_hook.lower():
        title = f"{raw_hook[:85]} #Shorts"
    else:
        title = raw_hook[:95]

    # 2. UNIQUE RICH DESCRIPTION
    scene_summary = clip_info.get("scene_summary") or clip_info.get("seen") or clip_info.get("caption") or ""
    quote = clip_info.get("quote") or ""
    cta = clip_info.get("cta") or ""

    if not cta:
        ctas_en = [
            "👉 What would you do in this situation? Drop a comment below! 👇",
            "👉 Rate this moment from 1 to 10 in the comments! 👇",
            "👉 Did you notice what happened in the background? 👀",
            "👉 Would you survive this in GTA 6? Let me know below! 👇",
            "👉 Share this with a friend who is waiting for GTA 6! 🔥",
        ]
        ctas_hi = [
            "👉 Agar aap is situation me hote toh kya karte? Comment me batao! 👇",
            "👉 Is scene ko 1 se 10 me kitne number doge? Comment karo! 👇",
            "👉 Kya aapne notice kiya piche kya hua? 👀",
            "👉 Apne dosto ke sath share karo jo GTA 6 ka wait kar rahe hain! 🔥",
            "👉 GTA 6 me sabse pehle aap kya karoge? Niche batao! 👇",
        ]
        h_idx = abs(hash(raw_hook)) % 5
        cta = (ctas_hi if lang == "hi" else ctas_en)[h_idx]

    desc_lines = []
    if scene_summary:
        desc_lines.append(scene_summary)
    if quote:
        desc_lines.append(f'\n💬 "{quote}"')

    desc_lines.append(f"\n{cta}")
    desc_lines.append(f"🔔 Subscribe to @{ch_name} for daily viral GTA 6 clips!")

    # Attribution
    stream_title = clip_info.get("stream_title") or "GTA 6 Gameplay Stream"
    desc_lines.append(f"\n🎮 Streamer: {creator}\n🎬 Stream: {stream_title}")

    # Hashtags
    hashtags = clip_info.get("hashtags")
    if not hashtags or not isinstance(hashtags, list):
        clean_tag = re.sub(r"[^a-zA-Z0-9]", "", creator.lower())
        if lang == "hi":
            hashtags = ["#Shorts", "#GTA6", f"#{clean_tag}", "#GTA6Hindi", "#Gaming", "#Viral"]
        else:
            hashtags = ["#Shorts", "#GTA6", f"#{clean_tag}", "#Gaming", "#ViralShorts"]

    desc_lines.append("\n" + " ".join(hashtags))
    full_description = "\n".join(desc_lines)

    # 3. TAILORED YOUTUBE TAGS
    clean_tags = [t.replace("#", "").strip() for t in hashtags if t]
    base_tags = ["shorts", "gta6", "gta 6", "gaming", creator.lower()]
    if lang == "hi":
        base_tags += ["gta 6 hindi", "hindi gameplay", f"{creator.lower()} gta 6", "techno gamerz", "carryminati"]
    else:
        base_tags += ["gta 6 funny", "gta 6 moments", f"{creator.lower()} gta 6", "ishowspeed", "mrbeast"]

    combined_tags = []
    for t in clean_tags + base_tags:
        if t and t.lower() not in [x.lower() for x in combined_tags]:
            combined_tags.append(t)

    return title, full_description, combined_tags


def upload_and_schedule(youtube, mp4_path: Path, clip_info: dict, publish_at_dt: datetime.datetime, channel_profile: dict = None):
    """Uploads a video to YouTube Shorts: immediate public if publish_at_dt is None, or scheduled private."""
    if not mp4_path.exists():
        print(f"[error] Video file {mp4_path} not found")
        return None

    ch_profile = channel_profile or resolve_channel()
    title, desc, tags = format_rich_metadata(clip_info, ch_profile, mp4_path.stem)

    if publish_at_dt is None:
        status_dict = {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        }
        iso_publish = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        is_immediate = True
    else:
        iso_publish = publish_at_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        status_dict = {
            "privacyStatus": "private",
            "publishAt": iso_publish,
            "selfDeclaredMadeForKids": False,
        }
        is_immediate = False

    body = {
        "snippet": {
            "title": title,
            "description": desc,
            "tags": tags[:30],  # YouTube API accepts up to ~500 chars of tags
            "categoryId": "20",  # Gaming
        },
        "status": status_dict,
    }

    media = MediaFileUpload(str(mp4_path), mimetype="video/mp4", resumable=True)
    ch_display = ch_profile.get("display_name", "Ghost Clips")
    print(f"\n[uploading -> {ch_display}] {mp4_path.name}")
    print(f"  Title: {title}")
    if is_immediate:
        print(f"  Status: 🔥 GOING LIVE IMMEDIATELY (PUBLIC)!")
    else:
        print(f"  Scheduled Live: {iso_publish} UTC (in {round((publish_at_dt - datetime.datetime.now(datetime.timezone.utc)).total_seconds() / 3600, 1)} hours)")

    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    retry_count = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"  Uploading... {int(status.progress() * 100)}%")
        except Exception as exc:
            err_msg = str(exc)
            if "quotaExceeded" in err_msg or "uploadLimitExceeded" in err_msg:
                print(f"\n[quota] YouTube daily upload quota limit reached for {ch_display}: {exc}")
                print(f"[quota] Local video {mp4_path.name} preserved safely for tomorrow's quota reset.")
                if hasattr(media, "_fd") and media._fd:
                    try:
                        media._fd.close()
                    except Exception:
                        pass
                return None
            retry_count += 1
            if retry_count > 3:
                print(f"[error] Upload failed for {mp4_path.name} after 3 retries: {exc}")
                raise
            print(f"[retry] Transient upload error ({exc}), retrying in 5 seconds... ({retry_count}/3)")
            time.sleep(5)

    video_id = response.get("id")
    if is_immediate:
        print(f"[ok] Video is now LIVE on {ch_display}! https://youtu.be/{video_id}")
    else:
        print(f"[ok] Video scheduled to {ch_display}! https://youtu.be/{video_id}")

    # Immediately delete local MP4 to save disk space
    try:
        file_size_mb = mp4_path.stat().st_size / (1024 * 1024)
        if hasattr(media, "_fd") and media._fd:
            try:
                media._fd.close()
            except Exception:
                pass
        del media
        del request
        gc.collect()
        mp4_path.unlink()
        print(f"[clean] Deleted local file: {mp4_path.name} (freed {file_size_mb:.1f} MB)")
    except Exception as exc:
        print(f"[warning] Could not delete {mp4_path}: {exc}")

    # Record in channel's queue log
    log_entry = {
        "channel": ch_profile.get("id", "ghost_clips"),
        "channel_name": ch_display,
        "video_id": video_id,
        "title": title,
        "publish_at": iso_publish,
        "privacy_status": "public" if is_immediate else "private",
        "is_immediate": is_immediate,
        "scheduled_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "url": f"https://youtu.be/{video_id}",
    }
    queue = load_queue_log(channel=ch_profile)
    queue.append(log_entry)
    save_queue_log(queue, channel=ch_profile)

    return log_entry


def process_folder(outdir: Path, channel=None, first_immediate=True):
    """Processes all rendered MP4s in a folder and schedules them to YouTube for the specified channel."""
    outdir = Path(outdir)
    clips_json_path = outdir / "clips.json"
    if not clips_json_path.exists():
        print(f"[error] No clips.json found in {outdir}")
        return []

    try:
        data = json.loads(clips_json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[error] Failed to parse {clips_json_path}: {exc}")
        return []

    clips = data.get("clips", [])
    creator = (data.get("source") or {}).get("name") or "Streamer"
    stream_title = (data.get("source") or {}).get("title") or "GTA 6 Stream"

    # Find pending MP4s
    pending = []
    for c in clips:
        for f in c.get("files", []):
            mp4_file = outdir / f["file"]
            if mp4_file.exists():
                c_copy = dict(c)
                c_copy["creator"] = creator
                c_copy["stream_title"] = stream_title
                pending.append((mp4_file, c_copy))

    if not pending:
        print(f"[info] No unuploaded MP4s in {outdir}")
        return []

    ch_profile = resolve_channel(channel)
    ch_display = ch_profile.get("display_name", "Ghost Clips")
    print(f"\n[schedule] Found {len(pending)} clip(s) for channel: '{ch_display}' ({outdir.name})")
    youtube = get_authenticated_service(channel=ch_profile)

    slots = calculate_next_slots(len(pending), channel=ch_profile, interval_hours=3, first_immediate=first_immediate)
    results = []
    for (mp4_file, clip_info), slot in zip(pending, slots):
        res = upload_and_schedule(youtube, mp4_file, clip_info, slot, channel_profile=ch_profile)
        if res:
            results.append(res)

    return results
    """Processes all rendered MP4s in a folder and schedules them to YouTube for the specified channel."""
    outdir = Path(outdir)
    clips_json_path = outdir / "clips.json"
    if not clips_json_path.exists():
        print(f"[error] No clips.json found in {outdir}")
        return []

    try:
        data = json.loads(clips_json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[error] Failed to parse {clips_json_path}: {exc}")
        return []

    clips = data.get("clips", [])
    creator = (data.get("source") or {}).get("name") or "Streamer"
    stream_title = (data.get("source") or {}).get("title") or "GTA 6 Stream"

    # Find pending MP4s
    pending = []
    for c in clips:
        for f in c.get("files", []):
            mp4_file = outdir / f["file"]
            if mp4_file.exists():
                c_copy = dict(c)
                c_copy["creator"] = creator
                c_copy["stream_title"] = stream_title
                pending.append((mp4_file, c_copy))

    if not pending:
        print(f"[info] No unuploaded MP4s in {outdir}")
        return []

    ch_profile = resolve_channel(channel)
    ch_display = ch_profile.get("display_name", "Ghost Clips")
    print(f"\n[schedule] Found {len(pending)} clip(s) for channel: '{ch_display}' ({outdir.name})")
    youtube = get_authenticated_service(channel=ch_profile)

    slots = calculate_next_slots(len(pending), channel=ch_profile, interval_hours=3)
    results = []
    for (mp4_file, clip_info), slot in zip(pending, slots):
        res = upload_and_schedule(youtube, mp4_file, clip_info, slot, channel_profile=ch_profile)
        if res:
            results.append(res)

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Multi-Channel YouTube Scheduler")
    sub = parser.add_subparsers(dest="cmd")

    p_auth = sub.add_parser("auth", help="Authorize a YouTube channel")
    p_auth.add_argument("--channel", default="ghost_clips", help="Channel name or alias (e.g. 'ghost clips' or 'gta 6 clips')")

    p_status = sub.add_parser("status", help="Check scheduled queue for a channel")
    p_status.add_argument("--channel", default=None, help="Channel name or alias (omit to see all)")

    p_sched = sub.add_parser("schedule", help="Schedule MP4s in a folder")
    p_sched.add_argument("folder", help="Path to clip folder containing clips.json")
    p_sched.add_argument("--channel", default="ghost_clips", help="Target YouTube channel")

    args = parser.parse_args()

    if args.cmd == "auth":
        ch = resolve_channel(args.channel)
        get_authenticated_service(channel=ch)
        print(f"Authentication complete for channel: {ch.get('display_name')}!")
    elif args.cmd == "status":
        if args.channel:
            ch_list = [resolve_channel(args.channel)]
        else:
            ch_data = load_channels()
            ch_list = list(ch_data.get("channels", {}).values())

        for ch in ch_list:
            q = load_queue_log(channel=ch)
            print(f"\n=== Channel: {ch.get('display_name')} ({ch.get('language', 'en').upper()}) ===")
            print(f"Total scheduled videos logged: {len(q)}")
            for item in q[-6:]:
                print(f"  {item.get('publish_at')} | {item.get('title')} | {item.get('url')}")
    elif args.cmd == "schedule":
        process_folder(Path(args.folder), channel=args.channel)
    else:
        parser.print_help()
