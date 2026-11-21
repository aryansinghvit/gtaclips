"""Autonomous YouTube Shorts Scheduler & Disk Cleaner for BeyondGTAClips.

Schedules clips to YouTube Shorts at 3-hour intervals (up to 6 clips per day),
automatically appending new clips after the last scheduled video slot.
Immediately deletes the local MP4 and intermediate cache once scheduled.
"""

import datetime
import gc
import json
import os
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
CLIENT_SECRETS_FILE = CONFIG_DIR / "client_secrets.json"
TOKEN_FILE = CONFIG_DIR / "token.json"
QUEUE_LOG = CONFIG_DIR / "scheduled_queue.json"


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def get_authenticated_service():
    """Authenticates using stored token.json, or guides one-time authorization."""
    ensure_config_dir()
    creds = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception as exc:
            print(f"[warning] Failed to load token.json: {exc}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
            except Exception as exc:
                print(f"[warning] Refreshing token failed: {exc}")
                creds = None

        if not creds:
            if not CLIENT_SECRETS_FILE.exists():
                print(f"\n[MISSING] client_secrets.json not found in:\n  {CLIENT_SECRETS_FILE}")
                print("\nPlease place your Google Cloud OAuth client_secrets.json there and run:")
                print("  py -3.13 beyondgtaclips.py youtube-auth\n")
                sys.exit(1)

            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_FILE), SCOPES)
            message = (
                "\n=======================================================\n"
                "PLEASE OPEN THIS URL IN YOUR BROWSER TO AUTHORIZE:\n"
                "{url}\n"
                "=======================================================\n"
            )
            creds = flow.run_local_server(
                port=8080,
                prompt="consent",
                access_type="offline",
                authorization_prompt_message=message,
                open_browser=True,
            )
            TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
            print(f"[ok] YouTube credentials authorized and saved to {TOKEN_FILE}", flush=True)

    return build("youtube", "v3", credentials=creds)


def load_queue_log():
    if QUEUE_LOG.exists():
        try:
            return json.loads(QUEUE_LOG.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_queue_log(queue):
    ensure_config_dir()
    QUEUE_LOG.write_text(json.dumps(queue, indent=2, default=str), encoding="utf-8")


def get_initial_start_time():
    """Finds the next clean 3-hour milestone (e.g. 12:00, 15:00, 18:00...) in local time."""
    local_now = datetime.datetime.now().astimezone()
    milestones = [0, 3, 6, 9, 12, 15, 18, 21]
    target = None
    for h in milestones:
        candidate = local_now.replace(hour=h, minute=0, second=0, microsecond=0)
        if candidate > local_now + datetime.timedelta(minutes=5):
            target = candidate
            break
    if target is None:
        tomorrow = local_now + datetime.timedelta(days=1)
        target = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
    return target.astimezone(datetime.timezone.utc)


# 6 slots per day starting at 12:00 PM local time:
# Slot 1: 12:00 PM (+0h)
# Slot 2: 06:00 PM (+6h)
# Slot 3: 09:00 PM (+9h)
# Slot 4: 12:00 AM Midnight (+12h)
# Slot 5: 06:00 AM (+18h)
# Slot 6: 09:00 AM (+21h)
DAILY_OFFSETS_HOURS = [0, 6, 9, 12, 18, 21]


def calculate_next_slots(count, interval_hours=3):
    """Calculates strictly 6 slots per day: 12 PM, 6 PM, 9 PM, 12 AM, 6 AM, 9 AM."""
    queue = load_queue_log()
    local_now = datetime.datetime.now().astimezone()

    latest_dt = None
    for item in queue:
        try:
            dt = datetime.datetime.fromisoformat(item["publish_at"].replace("Z", "+00:00")).astimezone()
            if latest_dt is None or dt > latest_dt:
                latest_dt = dt
        except Exception:
            pass

    slots = []
    # If the queue has future scheduled clips, continue seamlessly from the end of the queue
    if latest_dt and latest_dt > local_now + datetime.timedelta(minutes=10) and len(queue) > 0:
        already_scheduled = len(queue)
        first_item = queue[0]
        first_dt = datetime.datetime.fromisoformat(first_item["publish_at"].replace("Z", "+00:00")).astimezone()
        base_date = first_dt.date()

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
                    if len(candidate_slots) == count:
                        break
            if len(candidate_slots) == count:
                break
        slots = candidate_slots

    return slots


def upload_and_schedule(youtube, mp4_path: Path, clip_info: dict, publish_at_dt: datetime.datetime):
    """Uploads a video to YouTube Shorts as private with publishAt set."""
    if not mp4_path.exists():
        print(f"[error] Video file {mp4_path} not found")
        return None

    # Format Title: Hook text (strip markdown stars), add #Shorts, keep under 100 chars
    raw_hook = (clip_info.get("hook") or clip_info.get("title") or mp4_path.stem).replace("*", "")
    title = f"{raw_hook[:85]} #Shorts"

    # Description
    desc = clip_info.get("caption") or ""
    tags = clip_info.get("hashtags") or ["#gta6", "#Shorts", "#gaming"]
    if isinstance(tags, list):
        desc += "\n\n" + " ".join(tags)
    creator = clip_info.get("creator") or "BeyondGTAClips"
    desc += f"\n\n🎮 Credit: {creator}\nClip generated automatically by Beyond GTA Clips."

    iso_publish = publish_at_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    body = {
        "snippet": {
            "title": title,
            "description": desc,
            "tags": [t.replace("#", "") for t in tags] + ["shorts", "gta6", "gaming"],
            "categoryId": "20",  # Gaming
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": iso_publish,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(mp4_path), mimetype="video/mp4", resumable=True)
    print(f"\n[uploading] {mp4_path.name}")
    print(f"  Title: {title}")
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
                print(f"\n[quota] YouTube daily upload quota limit reached: {exc}")
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
    print(f"[ok] Video scheduled! https://youtu.be/{video_id}")

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

    # Record in queue log
    log_entry = {
        "video_id": video_id,
        "title": title,
        "publish_at": iso_publish,
        "scheduled_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "url": f"https://youtu.be/{video_id}",
    }
    queue = load_queue_log()
    queue.append(log_entry)
    save_queue_log(queue)

    return log_entry


def process_folder(outdir: Path):
    """Processes all rendered MP4s in a folder and schedules them to YouTube."""
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
    creator = (data.get("source") or {}).get("name") or "IShowSpeed"

    # Find pending MP4s
    pending = []
    for c in clips:
        for f in c.get("files", []):
            mp4_file = outdir / f["file"]
            if mp4_file.exists():
                c_copy = dict(c)
                c_copy["creator"] = creator
                pending.append((mp4_file, c_copy))

    if not pending:
        print(f"[info] No unuploaded MP4s in {outdir}")
        return []

    print(f"\n[schedule] Found {len(pending)} clip(s) to schedule from {outdir.name}")
    youtube = get_authenticated_service()

    slots = calculate_next_slots(len(pending), interval_hours=3)
    results = []
    for (mp4_file, clip_info), slot in zip(pending, slots):
        res = upload_and_schedule(youtube, mp4_file, clip_info, slot)
        if res:
            results.append(res)

    return results


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "auth":
        get_authenticated_service()
        print("Authentication complete!")
    elif len(sys.argv) > 1 and sys.argv[1] == "status":
        q = load_queue_log()
        print(f"\nTotal scheduled videos logged: {len(q)}")
        for item in q[-10:]:
            print(f"  {item.get('publish_at')} | {item.get('title')} | {item.get('url')}")
    elif len(sys.argv) > 2 and sys.argv[1] == "schedule":
        process_folder(Path(sys.argv[2]))
    else:
        print("Usage:")
        print("  py -3.13 youtube_scheduler.py auth")
        print("  py -3.13 youtube_scheduler.py status")
        print("  py -3.13 youtube_scheduler.py schedule <folder_path>")
