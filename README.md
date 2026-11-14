# YouTube Ambience Automation 🌧️☕

A daily bot that runs a faceless ambience YouTube channel. Every day at 12:00 UTC (GitHub Actions) it:

1. Picks **2 random topics** from 10 (rain window, cozy fireplace, lofi cafe night, snow, thunderstorm, library, train, ocean, autumn rain, campfire).
2. For each topic, downloads an **unused Pixabay stock clip with audio** and:
   - loops it into a **10-minute 16:9 video**, and
   - downloads a *second* clip, loops it to 30s and crops it to a **1080×1920 Short**.
3. Asks **Gemini Flash-Lite** for a title, description and tags.
4. Uploads both to YouTube **scheduled** to go public at peak times (4 uploads/day):
   Shorts at 16:00 & 23:30 UTC, long-form at 22:00 & 01:00 UTC (US afternoon/evening).
5. Records each used Pixabay ID in `used_video_ids.txt` (committed back by the workflow) so clips aren't repeated.

## Structure

```text
.github/workflows/daily_upload.yml   # Daily cron + manual trigger
src/script_generator.py              # Gemini metadata (with fallback text)
src/video_transformer.py             # Pixabay download, looping, 9:16 crop
src/youtube_uploader.py              # OAuth refresh-token upload, retries
main.py                              # Orchestration (topics, counts, durations)
get_refresh_token.py                 # One-time: create YT_REFRESH_TOKEN
used_video_ids.txt                   # Pixabay clips already used
```

## Setup

1. `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
2. `cp .env.example .env` and fill in `GEMINI_API_KEY`, `PIXABAY_API_KEY`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`.
3. `python get_refresh_token.py` and sign in with the channel owner's Google account.
4. Test locally: `python main.py`
5. In GitHub → Settings → Secrets and variables → Actions, add all 5 values as secrets.

## Google Cloud requirements

- YouTube Data API v3 enabled; OAuth client type **Desktop app**.
- OAuth consent screen **published to Production** (in "Testing" the refresh token expires after 7 days).
- Until the project passes YouTube's API audit, uploads are locked to **private**. Apply via the YouTube API Services audit form.
- Quota: 10,000 units/day; each upload costs 1,600, so 4 uploads/day leaves headroom for retries.

## Tuning

- Topics / uploads per day / long-form length: `main.py`
- Publish times: `PUBLISH_SLOTS_UTC` in `main.py`
- Schedule: `cron` in `.github/workflows/daily_upload.yml`
