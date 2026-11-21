# Instagram Reels bot

Two faceless Instagram accounts, 2 Reels a day each, made and posted for free by GitHub Actions
(`.github/workflows/instagram_reels.yml`).

| Account | Format | Posts (UTC) |
|---|---|---|
| `quiz` | Guess the Place: footage of a famous place, 4 options, 5 s countdown, reveal + fact | 13:30, 23:30 |
| `stoic` | Real Stoic quote revealed line by line, author, then an original "today, this means" line | 01:30, 16:00 |

Every Reel is checked before posting (1080x1920, H.264/AAC, -14 LUFS). Used clips and quotes are logged in
`reels/used_*.txt` so nothing repeats.

## Secrets (repo Settings → Secrets → Actions)

| Secret | What |
|---|---|
| `GEMINI_API_KEY`, `PIXABAY_API_KEY` | Already set (shared with the YouTube bot) |
| `IG_TOKEN_QUIZ` | Instagram long-lived token for the quiz account |
| `IG_TOKEN_STOIC` | Instagram long-lived token for the Stoic account |
| `GH_PAT` | Fine-grained GitHub token, this repo only, permission **Secrets: Read and write**. Lets the bot renew the Instagram tokens before their 60 days run out |

Without an account's token, runs only render the Reel and save it under the run's **Artifacts**.

## Test by hand

Actions → Instagram Reels → Run workflow → pick the account, keep **dry run** ticked to only render, untick to post.
