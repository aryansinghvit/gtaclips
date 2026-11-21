# Workspace Instructions: GTA 6 Clipping & YouTube Automation

## YouTube Channel Profiles
The user manages two distinct YouTube channels:
1. **Ghost Clips** (`ghost_clips`):
   - Audience: English
   - Target Creators: IShowSpeed, MrBeast, Kai Cenat, xQc, international streamers.
2. **GTA 6 Clips** (`gta6_clips`):
   - Audience: Hindi / Indian
   - Target Creators: Techno Gamerz, CarryMinati, Total Gaming, Mythpat, Indian streamers.

## Multi-Channel Routing Rules
- When the user says *"make gta 6 clips on ghost clips"* $\rightarrow$ target `--channel "ghost clips"`.
- When the user says *"make gta 6 clips on gta 6 clips"* $\rightarrow$ target `--channel "gta 6 clips"`.
- When the user links a stream and specifies the channel (e.g. *"post on gta 6 clips"* or *"post on ghost clips"*) $\rightarrow$ target that channel.
- **CHANNEL CLARIFICATION RULE**: If the user does NOT specify a channel (e.g. simply says *"make gta 6 clips"* or pastes a link without naming a channel), **prompt the user with a quick clarification question**:
  *"Which channel should I post these clips to?*
   *1. Ghost Clips (English)*
   *2. GTA 6 Clips (Hindi)"*
  Wait for the user's choice before initiating the clipping and scheduling pipeline.

## User Default Preferences (Permanent & Non-interactive once channel is confirmed)
1. **Clips Count**: 5–6 clips per 1 hour of stream video (e.g., 8-hour stream produces ~40–48 clips; 1 hour produces 6 clips).
2. **Stream Discovery Recency**: Last 48 hours (`within: 48h`).
3. **Style**: **Stack** (`stack`: facecam on top, hook card divider, full gameplay below).
4. **YouTube Publishing Slots**:
   - **Immediate 1st Clip**: When the 1st clip is ready, publish it **immediately** (Public) to the channel.
   - **Subsequent Clips**: From the 2nd clip onward, schedule across the 6 daily slots:
     - Slot 1: 12:00 PM
     - Slot 2: 06:00 PM
     - Slot 3: 09:00 PM
     - Slot 4: 12:00 AM (Midnight)
     - Slot 5: 06:00 AM
     - Slot 6: 09:00 AM
5. **Disk Storage**: Purge local `.mp4` video files immediately after upload.
6. **Unique Metadata**: Every clip must have a distinct hook title, transcript-derived scene synopsis, dialogue quote, rotating call-to-action question, and channel-tailored tags.
