---
description: Permanent defaults for GTA 6 clipping, multi-channel YouTube routing, and scheduling
trigger: always_on
---

# User Default Preferences for Clipping & Multi-Channel YouTube Scheduling

## YouTube Channel Profiles
The user manages two distinct YouTube channels:
1. **Ghost Clips** (`ghost_clips`): English channel targeting international creators (IShowSpeed, MrBeast, Kai Cenat, xQc).
2. **GTA 6 Clips** (`gta6_clips`): Hindi channel targeting Indian gaming creators (Techno Gamerz, CarryMinati, Total Gaming).

## Multi-Channel Routing Rules
- When the user says *"make gta 6 clips on ghost clips"* $\rightarrow$ target `--channel "ghost clips"`.
- When the user says *"make gta 6 clips on gta 6 clips"* $\rightarrow$ target `--channel "gta 6 clips"`.
- When the user links a stream and specifies the channel (e.g. *"post on gta 6 clips"* or *"post on ghost clips"*) $\rightarrow$ target that channel.
- **CHANNEL CLARIFICATION RULE**: If the user does NOT specify a channel (e.g. simply says *"make gta 6 clips"* or pastes a link without naming a channel), **prompt the user with a quick clarification question**:
  *"Which channel should I post these clips to?*
   *1. Ghost Clips (English)*
   *2. GTA 6 Clips (Hindi)"*
  Wait for the user's choice before initiating the clipping and scheduling pipeline.

## Locked-In Defaults (Follow automatically once channel is known):
1. **Clips per hour**:
   - Strictly 5 to 6 clips per 1 hour of stream video (e.g., an 8-hour stream produces 40–48 clips; 1 hour produces 6 clips).
   - Slice streams into consecutive 1-hour chunks (`0-60m`, `60-120m`, etc.).
2. **Stream Discovery Recency**:
   - Last 48 hours (`within: 48h`).
3. **Video Style / Template**:
   - **Stack** style (Style #2: streamer facecam boxed on top, hook text divider in middle, full gameplay below).
4. **YouTube Publishing Schedule**:
   - Exactly 6 clips per day across these 6 slots:
     - Slot 1: 12:00 PM (Noon)
     - Slot 2: 06:00 PM (Evening prime)
     - Slot 3: 09:00 PM (Night prime)
     - Slot 4: 12:00 AM (Midnight)
     - Slot 5: 06:00 AM (Early morning)
     - Slot 6: 09:00 AM (Morning prime)
   - Automatically roll over subsequent clips to future days (Day 1: Slots 1–6, Day 2: Slots 1–6, etc.).
5. **Immediate Disk Cleanup**:
   - Delete local `.mp4` video files immediately after upload to save laptop storage space.
6. **Unique Metadata**:
   - Every clip must have a distinct hook title, transcript-derived scene synopsis, dialogue quote, rotating call-to-action question, and channel-tailored tags.
