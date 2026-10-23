# Free Daily YouTube Shorts (starter)

This starter is designed to run in GitHub Actions while your PC is off. It creates one vertical Short per scheduled run using:
- Gemini API free tier (API key required; free quotas apply)
- Python + Pillow + FFmpeg
- gTTS for narration (free community service; availability/terms can change)
- Optional YouTube Data API upload (OAuth setup required)

**No paid service is required by this code, but free services have quotas and can change.** The workflow skips uploading unless `YOUTUBE_UPLOAD` is set to `true` and OAuth secrets are configured. First test with upload disabled.

## What it makes
A simple narrated, text-led vertical video (not AI-generated cinematic footage), plus title/description/hashtags and the source script. Default niche: fresher careers, office life, discipline, and personal growth.

## 1. Create a GitHub repository
1. Create a new GitHub repository. Public is simplest for avoiding Actions-minute limits on standard runners, but do not put credentials in files.
2. Upload these files to the repository, keeping the folder structure.
3. Open **Settings → Secrets and variables → Actions → New repository secret**.
4. Add `GEMINI_API_KEY` using a key from Google AI Studio. Check the current free-tier limits for the selected model in your region.

## 2. Test generation first
Go to **Actions → Daily YouTube Short → Run workflow**.
Initially, leave `YOUTUBE_UPLOAD` unset/false. Download the workflow artifact named `daily-short` and inspect the MP4 and `content.json`.

## 3. Schedule
The workflow is scheduled for 03:30 UTC, which is 09:00 India Standard Time. GitHub may delay scheduled jobs during busy periods, so 9:00 is not guaranteed to the minute.

## 4. Optional YouTube upload (extra setup)
Automatic uploads require YouTube Data API OAuth. A Google AI Studio API key is **not** a YouTube upload credential.
1. In Google Cloud Console, create/select a project, enable **YouTube Data API v3**, configure OAuth consent, and create an OAuth client of type **Desktop app**.
2. Download the OAuth client JSON to your own PC as `client_secret.json`.
3. On your PC, create a Python environment and install the requirements: `pip install -r requirements.txt`.
4. Run `python youtube_auth.py`. Complete Google's consent screen for the YouTube channel you intend to use. It creates `token.json`.
5. Encode both files as Base64 in PowerShell:
   - `(Get-Content .\client_secret.json -Raw | % { [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($_)) })`
   - `(Get-Content .\token.json -Raw | % { [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($_)) })`
   Copy each output separately.
6. Add GitHub Actions secrets:
   - `YOUTUBE_CLIENT_SECRET_B64` = Base64 of `client_secret.json`
   - `YOUTUBE_TOKEN_B64` = Base64 of `token.json`
7. Add repository variable `YOUTUBE_UPLOAD` = `true`.

**Security:** Never commit API keys, OAuth JSON, or token files. Keep the repo secrets private to you. Google may restrict uploads from unverified API projects to private visibility; check current Google/YouTube rules. The uploader defaults to **private** visibility. Change `YOUTUBE_PRIVACY_STATUS` only after you've tested the pipeline and understand the policy.

## 5. Important limitations
- This does not use your Gemini Pro app subscription directly. It uses a Gemini API key; API free quotas are separate from the consumer subscription.
- gTTS depends on a third-party online service and is not guaranteed or unlimited. If it fails, the workflow fails and can be retried.
- The video uses narrated text cards, not generated B-roll or an avatar. This keeps the workflow lightweight and low-cost.
- A scheduled workflow can be delayed or skipped by GitHub. Check Actions history.
- Don't upload unreviewed AI content blindly. Review copyright, factual claims, repetitive/low-value content, and YouTube monetization policies before enabling public publication.
