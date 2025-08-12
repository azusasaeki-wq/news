# VC Investment Radar (no-Feedly)
Track **investment announcements** from selected VCs without using Feedly. 
It pulls official **News/Press** feeds (RSS where available, simple HTML scrape otherwise), 
deduplicates, and generates a daily digest (Markdown + JSON). Optional: push to Slack.

## Quick start (GitHub Actions)
1. **Create a new GitHub repo**, then upload these files.
2. Push to `main`. GitHub Actions will run daily (UTC) and write digests to `output/`.
3. (Optional) Set a Slack Incoming Webhook in repo **Settings → Secrets and variables → Actions**:
   - `SLACK_WEBHOOK_URL`: your Slack webhook URL.

### Local run
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/fetch.py
```
Artifacts are written to `output/`.

## Configuration
Edit `config/sources.yml` to add/remove firms. 
Two kinds of sources per firm:
- `rss`: list of RSS/Atom feed URLs (preferred; most reliable)
- `pages`: list of **News/Press** page URLs (fallback scraper). Scraper is generic and may need tweaks.

You can also adjust keyword filters to **only keep likely investment announcements**.

## Output
- `output/digest_YYYY-MM-DD.md` — human-readable digest
- `output/latest.json` — machine-readable latest items
- `data/db.json` — local cache for de-duplication

## Notes / Caveats
- HTML structures change. If a site redesigns, update `config/sources.yml` or rely on RSS.
- This is a lightweight scraper; obey sites' Terms/robots.txt if you self-host. Keep polling moderate (default daily).
- GitHub Actions uses UTC. Adjust the `cron` in `.github/workflows/daily.yml` if you want a different time.

## Add Slack channel notifications
Set `SLACK_WEBHOOK_URL` secret. The job will send a brief summary when new items are found.

---

Made for tracking **investment announcements** across:
- a16z, Sequoia, Accel, Index, Lightspeed, Greylock, Benchmark, Bessemer, Balderton, Atomico
- YC, Techstars, 500 Global, Antler, NFX, Seedcamp, LocalGlobe

You control everything — no external SaaS.
