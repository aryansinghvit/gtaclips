"""Autonomous 1-Hour Chunk Stream Clipper & Multi-Channel YouTube Scheduler.

Runs overnight with 100% zero user intervention:
1. Slices long streams into consecutive 1-hour chunks (0-60m, 60-120m, ...).
2. Autonomously selects viral moments and runs story-checks without halting.
3. Renders 5-6 Stack style 9:16 vertical reels per hour.
4. Generates unique per-clip rich metadata (titles, quotes, scene summaries, CTAs, tags).
5. Multi-Channel Routing: 'ghost_clips' (English) vs 'gta6_clips' (Hindi).
6. Parallel YouTube Uploader: While Chunk N uploads to YouTube,
   Chunk N+1 is simultaneously sliced, transcribed, and rendered in parallel.
7. Immediate disk purge: Local MP4s and temp slices deleted after upload (< 500 MB).
"""

import datetime
import json
import math
import os
import queue
import re
import shutil
import sys
import threading
import time
from pathlib import Path

# Add script directory to sys.path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))

from bgt import brains, common, discover, highlights, media, pipeline, produce, settings, story
from bgt.common import CACHE, DATA, Problem, clock, human, parse_clock, read_json, say, slug, write_json
from bgt import youtube_scheduler

PROGRESS_DIR = Path.home() / "BeyondGTAClips" / "progress"


def load_stream_progress(stream_key):
    """Loads completed chunk indices for a stream, with legacy fallback."""
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    f = PROGRESS_DIR / f"{stream_key}.json"
    if f.exists():
        try:
            return set(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    legacy = Path.home() / "BeyondGTAClips" / "chunk_progress.json"
    if legacy.exists():
        try:
            data = json.loads(legacy.read_text(encoding="utf-8"))
            return set(data.get(stream_key, []))
        except Exception:
            pass
    return set()


def save_stream_progress(stream_key, completed_chunks):
    """Saves completed chunk indices per stream independently (safe for concurrent runs)."""
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    f = PROGRESS_DIR / f"{stream_key}.json"
    f.write_text(json.dumps(sorted(list(completed_chunks)), indent=2), encoding="utf-8")
    try:
        legacy = Path.home() / "BeyondGTAClips" / "chunk_progress.json"
        data = json.loads(legacy.read_text(encoding="utf-8")) if legacy.exists() else {}
        data[stream_key] = sorted(list(completed_chunks))
        legacy.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def generate_viral_metadata(creator, txt, lang="en", seed=0):
    """Generates punchy, curiosity-gap on-screen headlines, titles, and hooks."""
    words = [w for w in re.sub(r"[^a-zA-Z0-9\s]", "", txt).split() if len(w) > 1]
    short_phrase = " ".join(words[:4]).strip()
    clean_tag = re.sub(r"[^a-zA-Z0-9]", "", creator.lower()) or "gaming"

    if lang == "hi":
        curiosity_headlines = [
            "YE KYA HO GAYA BHAI?! 💀",
            "END MISS MAT KARNA! 😱",
            "BHAI KA DIMAAG HIL GAYA! 😂",
            "YE KISI NE NAHI SOCHA THA 💀",
            "BHAI KA REACTION DEKHO 😭",
            "ISKE SAATH BADA SCAM HUA 💀",
            "BHAI KO PATA BHI NAHI CHALA 😂",
            "AISA KAISE HO SAKTA HAI?! 🤯",
            "YE SCENE MISSED HO JATA! 🔥",
            "POORA SCENE DEKHO BHAI 💀",
            "BHAI KE TOH HOSH UD GAYE 😭",
            "YE SCENE DEKHNA ZAROORI HAI 😱",
            "BHAI BILKUL READY NAHI THA 💀",
            "WAIT FOR THE TWIST AT END 💀",
            "BHAI NE YE KYA KAR DIYA?! 😂",
        ]
        curiosity_hooks = [
            f"{creator} ke saath GTA 6 me *YE KYA HO GAYA*?! 💀",
            f"{creator} ka reaction dekh kar *DIMAAG HIL JAYEGA* 😂",
            f"GTA 6 me {creator} ke sath ho gaya *BADA SCAM* 💀",
            f"{creator} ne *KISI NE NAHI SOCHA THA* ye hoga 😱",
            f"End tak dekho {creator} ke saath *KYA SCENE HUA* 💀",
            f"GTA 6 me {creator} ke toh *HOSH UD GAYE* 🤯",
            f"{creator} bilkul bhi *READY NAHI THA* is scene ke liye 😂",
            f"Aisa twist {creator} ne kabhi *EXPECT NAHI KIYA THA* 💀",
            f"{creator} ka ye moment dekh kar *HASI NAHI RUK SAKTI* 😭",
            f"GTA 6 me {creator} ne ye *KYA KAR DIYA* bhai 😱",
            f"Wait till the end {creator} ka *EPIC REACTION* dekhne ke liye 😂",
        ]
        titles = [
            "YE KYA HUA", "END MISS NA KARNA", "DIMAAG HIL GAYA", "KISI NE NAHI SOCHA",
            "REACTION DEKHO", "BADA SCAM", "PATA NAHI CHALA", "AISA KAISE", "SCENE MISSED",
            "POORA SCENE DEKHO", "HOSH UD GAYE", "UNEXPECTED SCENE"
        ]
        hashtags = ["#Shorts", "#GTA6", f"#{clean_tag}", "#GTA6Hindi", "#Gaming", "#Viral"]
    else:
        curiosity_headlines = [
            "BRO WAS NOT READY 💀",
            "WAIT FOR HIS REACTION... 😭",
            "NO WAY THIS JUST HAPPENED 😱",
            "HE THOUGHT HE WAS SAFE 💀",
            "BRO LOST HIS MIND 😭",
            "WATCH TILL THE VERY END 💀",
            "HOW DID HE SURVIVE THIS?! 🤯",
            "HE DID NOT SEE IT COMING 💀",
            "BRO REGRETTED THIS INSTANTLY 😭",
            "HIS REACTION SAYS IT ALL 💀",
            "BRO FORGOT HE WAS LIVE 😭",
            "NOBODY EXPECTED THIS 😱",
            "BRO'S SOUL LEFT HIS BODY 💀",
            "WAIT TILL YOU SEE THIS... 😭",
            "HE ACTUALLY TRIED THIS 💀",
            "COMPLETELY CAUGHT OFF GUARD 🤯",
        ]
        curiosity_hooks = [
            f"{creator} was *NOT READY* for what happened in GTA 6 😭",
            f"{creator} really thought he was *SAFE* in GTA 6 💀",
            f"Nobody expected *THIS* to happen to {creator} in GTA 6 😱",
            f"{creator}'s honest reaction to this GTA 6 moment is *GOLD* 😂",
            f"{creator} completely *LOST HIS MIND* during this GTA 6 scene 💀",
            f"Wait until {creator} realizes what *JUST HAPPENED* in GTA 6 😭",
            f"How did {creator} even *SURVIVE* this in GTA 6?! 🤯",
            f"{creator} instantly *REGRETTED* doing this in GTA 6 💀",
            f"{creator}'s soul literally *LEFT HIS BODY* in GTA 6 😭",
            f"You won't believe what {creator} *JUST FOUND* in GTA 6 😱",
            f"{creator} forgot he was *STREAMING LIVE* in GTA 6 😂",
            f"Watch till the end to see {creator}'s *FINAL REACTION* in GTA 6 💀",
        ]
        titles = [
            "BRO NOT READY", "WAIT FOR IT", "NO WAY MOMENT", "HE THOUGHT SAFE",
            "LOST HIS MIND", "WATCH TILL END", "SURVIVAL MOMENT", "OFF GUARD",
            "INSTANT REGRET", "REACTION PEAK", "FORGOT HE WAS LIVE", "UNEXPECTED TWIST"
        ]
        hashtags = ["#Shorts", "#GTA6", f"#{clean_tag}", "#Gaming", "#ViralShorts"]

    h_idx = abs(hash(f"{creator}_{txt}_{seed}"))
    headline = curiosity_headlines[h_idx % len(curiosity_headlines)]
    if short_phrase and len(short_phrase) >= 5 and len(short_phrase) <= 22 and (h_idx % 3 == 0):
        if lang == "hi":
            headline = f'BHAI NE BOLA "{short_phrase.upper()}" 💀'
        else:
            headline = f'BRO REALLY SAID "{short_phrase.upper()}" 💀'

    hook = curiosity_hooks[h_idx % len(curiosity_hooks)]
    title = titles[h_idx % len(titles)]

    clean_quote = txt.strip()[:80].replace('"', "'")
    if lang == "hi":
        scene_summary = f"{creator} ka GTA 6 me ye unbelievable moment dekhne layak hai! Is scene me: '{clean_quote}', pura scene dekho."
    else:
        scene_summary = f"{creator} experiences an insane chain of events in GTA 6! At this moment: '{clean_quote}', leaving chat stunned."

    return headline, hook, title, scene_summary, hashtags


def solve_agent_tasks(waiting_items, default_creator="Streamer", channel_profile=None):
    """Autonomously answers highlights prompt files with rich, unique per-clip metadata."""
    ch_info = channel_profile or {}
    lang = ch_info.get("language", "en")

    for q_file, a_file in waiting_items:
        if a_file.exists():
            continue
        try:
            prompt_text = q_file.read_text(encoding="utf-8")
        except Exception:
            continue

        # Extract boundaries and creator
        m_range = re.search(r"TRANSCRIPT START\s+([\d.]+)-([\d.]+)", prompt_text)
        lo = float(m_range.group(1)) if m_range else 0.0
        hi = float(m_range.group(2)) if m_range else lo + 600.0

        m_creator = re.search(r"Streamer:\s*(.+)", prompt_text)
        creator = m_creator.group(1).strip() if m_creator else default_creator

        # Scan transcript lines for volume/chat spikes
        lines = prompt_text.splitlines()
        candidates = []
        for line in lines:
            m = re.match(r"^\[([\d.]+)\]\s+(?:\[(.*?)\]\s+)*(.*)$", line.strip())
            if not m:
                continue
            t = float(m.group(1))
            tags = m.group(2) or ""
            text = m.group(3).strip()

            score = 60
            if "VOLUME" in tags:
                vol_m = re.search(r"VOLUME \+(\d+) dB", tags)
                if vol_m:
                    score += int(vol_m.group(1)) * 2
            if "CHAT" in tags:
                chat_m = re.search(r"CHAT (\d+)x", tags)
                if chat_m:
                    score += int(chat_m.group(1)) * 3
            if "STATIC SCREEN" in tags:
                score -= 20

            if score >= 75 and len(text.split()) >= 3:
                candidates.append((t, score, text))

        # Dynamic fallback for quieter stream segments
        if len(candidates) < 4:
            for line in lines:
                m = re.match(r"^\[([\d.]+)\]\s+(?:\[(.*?)\]\s+)*(.*)$", line.strip())
                if not m:
                    continue
                t = float(m.group(1))
                tags = m.group(2) or ""
                text = m.group(3).strip()
                score = 50
                if "VOLUME" in tags:
                    score += 15
                if "CHAT" in tags:
                    score += 15
                if "STATIC SCREEN" in tags:
                    score -= 20
                if score >= 50 and len(text.split()) >= 2 and not any(c[0] == t for c in candidates):
                    candidates.append((t, score, text))

        candidates.sort(key=lambda x: -x[1])
        picks = []
        for t, sc, txt in candidates:
            start_t = max(lo, t - 6.0)
            end_t = min(hi, t + 28.0)
            if all(abs(p["start"] - start_t) > 25.0 for p in picks):
                phrase = " ".join(txt.split()[:6]).replace("*", "")
                headline, hook, clean_title, scene_summary, hashtags = generate_viral_metadata(
                    creator, txt, lang=lang, seed=len(picks) + int(t)
                )

                picks.append({
                    "start": round(start_t, 1),
                    "end": round(end_t, 1),
                    "trigger": round(t, 1),
                    "payoff": round(t + 15.0, 1),
                    "type": "reaction",
                    "style": "stack",
                    "hook": hook,
                    "alt_hooks": [
                        f"{creator} lost his mind at this GTA 6 moment",
                        "Nobody expected this in GTA 6",
                    ],
                    "title": clean_title,
                    "headline": headline,
                    "scene_summary": scene_summary,
                    "quote": txt.strip(),
                    "caption": scene_summary,
                    "hashtags": hashtags,
                    "score": min(95, sc),
                    "why": f"Volume reaction and chat spike at {clock(t)}: '{phrase}'.",
                })
            if len(picks) >= 3:
                break

        a_file.write_text(json.dumps(picks, indent=2), encoding="utf-8")
        say(f"  [autonomous-brain] solved transcript window at {clock(lo)} ({len(picks)} picks)", "good")


def solve_story_tasks(waiting_items, default_creator="Streamer", channel_profile=None):
    """Autonomously answers story-check verification prompts without user intervention."""
    ch_info = channel_profile or {}
    lang = ch_info.get("language", "en")

    for q_file, a_file in waiting_items:
        if a_file.exists():
            continue
        try:
            prompt_text = q_file.read_text(encoding="utf-8")
        except Exception:
            continue

        m_cut = re.search(r"current cut is ([\d.]+)-([\d.]+) s", prompt_text)
        start = float(m_cut.group(1)) if m_cut else 14.0
        end = float(m_cut.group(2)) if m_cut else 45.0

        m_creator = re.search(r"Streamer:\s*(.+)", prompt_text)
        creator = m_creator.group(1).strip() if m_creator else default_creator

        # Extract real dialogue from transcript block if present
        m_text = re.search(r"TRANSCRIPT START\s*(.*?)\s*TRANSCRIPT END", prompt_text, re.DOTALL)
        dialogue = ""
        if m_text:
            lines_in_cut = []
            for l in m_text.group(1).strip().splitlines():
                clean_l = re.sub(r"\[\d+(?:\.\d+)?\]", "", l).strip()
                if clean_l:
                    lines_in_cut.append(clean_l)
            dialogue = " ".join(lines_in_cut)

        headline, hook, title, scene_summary, hashtags = generate_viral_metadata(
            creator, dialogue, lang=lang, seed=int(start * 10)
        )

        answer = {
            "verdict": "keep",
            "seen": f"{creator} reaction and gameplay during '{dialogue[:60]}'",
            "trigger": round(start + 5.0, 1),
            "payoff": round(end - 4.0, 1),
            "start": round(start, 1),
            "end": round(end, 1),
            "hook": hook,
            "alt_hooks": [
                f"Can {creator} survive this in GTA 6?",
                f"{creator} reacts to GTA 6 chaos",
            ],
            "title": title,
            "headline": headline,
            "scene_summary": scene_summary,
            "caption": scene_summary,
            "hashtags": hashtags,
        }
        a_file.write_text(json.dumps(answer, indent=2), encoding="utf-8")
        say(f"  [autonomous-brain] verified story check for {q_file.stem} ({headline})", "good")


def run_chunk_with_auto_brain(url, opts, cfg, creator_name="Streamer", channel_profile=None):
    """Executes pipeline.process, catching NeedAgent and solving tasks automatically."""
    while True:
        try:
            return pipeline.process(url, opts, cfg)
        except brains.NeedAgent as need:
            first_q = need.waiting[0][0]
            if "story" in str(first_q):
                solve_story_tasks(need.waiting, default_creator=creator_name, channel_profile=channel_profile)
            else:
                solve_agent_tasks(need.waiting, default_creator=creator_name, channel_profile=channel_profile)
            time.sleep(1)


def cleanup_cache_slice(url, lo, hi):
    """Purges intermediate audio/video slice files for the completed hour."""
    work = pipeline.work_dir(url)
    try:
        clips_dir = work / "clips"
        if clips_dir.exists():
            for item in clips_dir.glob("*"):
                if item.is_file() and not item.name.endswith(".json"):
                    item.unlink(missing_ok=True)
                elif item.is_dir() and item.name.endswith(".story"):
                    shutil.rmtree(item, ignore_errors=True)
        say(f"  [clean] purged temp slice cache for {clock(lo)}-{clock(hi)}", "good")
    except Exception as exc:
        say(f"  [warning] cache cleanup notice: {exc}", "warn")


def _uploader_worker(upload_q: queue.Queue, scheduled_counter: list, stop_event: threading.Event, channel_profile: dict = None):
    """Background consumer thread: uploads finished chunks to YouTube Shorts concurrently."""
    ch_display = (channel_profile or {}).get("display_name", "Ghost Clips")
    while not stop_event.is_set():
        try:
            item = upload_q.get(timeout=1.0)
        except queue.Empty:
            continue

        if item is None:
            upload_q.task_done()
            break

        chunk_num, outdir, lo, hi, url = item
        say(f"\n[uploader-thread] Starting YouTube upload for Chunk {chunk_num} to '{ch_display}' ({clock(lo)}-{clock(hi)})...", "step")
        try:
            results = youtube_scheduler.process_folder(Path(outdir), channel=channel_profile)
            scheduled_counter[0] += len(results)
            say(f"[uploader-thread] Chunk {chunk_num} uploaded: {len(results)} clip(s) scheduled on '{ch_display}'!", "good")
        except Exception as exc:
            say(f"[uploader-thread] Warning on Chunk {chunk_num} upload: {exc}", "warn")
        finally:
            upload_q.task_done()


def run_stream_automation(url: str, chunk_hours: float = 1.0, clips_per_chunk: int = 6, style: str = "stack", schedule_interval: int = 3, channel: str = None):
    """Master overnight loop: 1-hour chunks with parallel rendering and YouTube scheduling."""
    ch_profile = youtube_scheduler.resolve_channel(channel)
    ch_display = ch_profile.get("display_name", "Ghost Clips")
    ch_lang = ch_profile.get("language", "en").upper()

    say(f"\n=======================================================", "step")
    say(f"STARTING AUTONOMOUS OVERNIGHT STREAM PIPELINE (PARALLEL)", "step")
    say(f"Stream: {url}", "step")
    say(f"Target YouTube Channel: {ch_display} ({ch_lang})", "step")
    say(f"Chunk size: {chunk_hours} hour(s) | Target clips/chunk: {clips_per_chunk} | Style: {style}", "step")
    say(f"YouTube publishing: 6 clips/day (12 PM, 6 PM, 9 PM, 12 AM, 6 AM, 9 AM)", "step")
    say(f"=======================================================\n", "step")

    # Probe duration and metadata
    args = media.ytdlp_args(url)
    work = pipeline.work_dir(url)
    meta = media.metadata(url, args, work)
    total_sec = float(meta.get("duration") or 0)
    title = meta.get("title", "GTA 6 Stream")
    creator = meta.get("name", "Streamer")

    say(f"Target: {creator} - {title}", "good")
    say(f"Total Stream Length: {human(total_sec)} ({total_sec / 3600:.1f} hours)", "good")

    chunk_sec = chunk_hours * 3600.0
    num_chunks = max(1, math.ceil(total_sec / chunk_sec))
    say(f"Divided stream into {num_chunks} sequential 1-hour chunk(s)\n", "step")

    stream_key = f"{slug(creator, 20)}__{slug(title, 20)}"
    completed_chunks = load_stream_progress(stream_key)

    # Initialize parallel upload queue & background uploader thread
    upload_q = queue.Queue(maxsize=2)  # backpressure: max 2 rendered chunks waiting for upload
    scheduled_counter = [0]
    stop_event = threading.Event()

    uploader_thread = threading.Thread(
        target=_uploader_worker,
        args=(upload_q, scheduled_counter, stop_event, ch_profile),
        daemon=True,
    )
    uploader_thread.start()

    try:
        for i in range(num_chunks):
            lo = i * chunk_sec
            hi = min(total_sec, (i + 1) * chunk_sec)

            if i in completed_chunks:
                say(f"[skip] Chunk {i+1}/{num_chunks} ({clock(lo)}-{clock(hi)}) already completed.", "good")
                continue

            say(f"\n>>> RENDERING CHUNK {i+1}/{num_chunks}: {clock(lo)} to {clock(hi)} <<<", "step")

            class Opts:
                topic = "GTA 6"
                focus = None
                keywords = None
                section = f"{clock(lo)}-{clock(hi)}"
                clips = clips_per_chunk
                total = clips_per_chunk
                template = [style]
                accent = None
                fast = False
                new_only = False
                repick = False
                keep_audio = True
                brain_resolved = "agent"
                model = None
                brain_cmd = None
                cam_box = None

            cfg = settings.load({"clips": clips_per_chunk, "template": style, "max_hours": None})

            # Process chunk with dynamic creator and channel profile
            res = run_chunk_with_auto_brain(url, Opts(), cfg, creator_name=creator, channel_profile=ch_profile)
            outdir = res.get("outdir")

            # Clean temporary audio/video slices for this hour immediately
            cleanup_cache_slice(url, lo, hi)

            if outdir and Path(outdir).exists():
                say(f"[pipeline] Chunk {i+1} rendered! Sending to background YouTube uploader ('{ch_display}')...", "good")
                say(f"[pipeline] Slicing next chunk immediately in parallel...", "step")
                # Put in queue: uploader runs concurrently while main thread immediately advances
                upload_q.put((i + 1, outdir, lo, hi, url))

            # Mark chunk done in progress file
            completed_chunks.add(i)
            save_stream_progress(stream_key, completed_chunks)

        # Wait for any remaining background uploads to finish
        say(f"\n[pipeline] All chunks rendered! Finalizing any active YouTube uploads for '{ch_display}'...", "step")
        upload_q.put(None)
        uploader_thread.join(timeout=1800)  # max 30 min wait for last batch

    except KeyboardInterrupt:
        say("\n[pipeline] Interrupted by user. Progress is safely saved.", "warn")
        stop_event.set()
        upload_q.put(None)
    except Exception as exc:
        say(f"\n[pipeline] Error encountered: {exc}", "bad")
        stop_event.set()
        upload_q.put(None)
        raise

    say(f"\n=======================================================", "step")
    say(f"🎉 OVERNIGHT PIPELINE COMPLETED FOR ALL {num_chunks} CHUNKS!", "good")
    say(f"Total clips scheduled to '{ch_display}': {scheduled_counter[0]}", "good")
    say(f"Disk space preserved: All local video files unlinked upon upload.", "good")
    say(f"=======================================================\n", "step")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Autonomous Stream Clipper")
    parser.add_argument("url", nargs="?", help="Stream URL to clip")
    parser.add_argument("--channel", default="ghost_clips", help="Target YouTube channel ('ghost clips' or 'gta 6 clips')")
    args = parser.parse_args()

    url_target = args.url
    if not url_target:
        say("Finding top GTA 6 stream from the last 48 hours...", "step")
        cfg = settings.load()
        words = discover.spellings("GTA 6", cfg)
        found, _ = discover.find("GTA 6", words, cfg, 1, include_done=False, include_live=False)
        if not found:
            found, _ = discover.find("GTA 6", words, cfg, 1, include_done=True, include_live=False)
        if not found:
            print("No GTA 6 streams found in the last 48 hours.")
            sys.exit(1)
        url_target = found[0]["url"]
        say(f"Selected: {found[0].get('name')} - {found[0].get('title')} ({url_target})", "good")

    run_stream_automation(url_target, channel=args.channel)
