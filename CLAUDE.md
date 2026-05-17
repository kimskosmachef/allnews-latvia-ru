# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A Telegram news aggregation bot that scrapes Russian-language Latvian news sites and publishes fresh articles to a Telegram channel (`@vse_novosti_lv`).

Repository: https://github.com/kimskosmachef/allnews-latvia-ru

Runs on a Hetzner CX23 VPS (Ubuntu 24.04, Finland) under user `newsbot`, managed by systemd service `newsbot.service`.

## Running

```bash
# Activate virtualenv first
source venv/bin/activate

# Run the bot
python bot.py
```

## Deployment (Hetzner VPS)

```bash
# Logs (follow)
journalctl -u newsbot -f

# Restart service
sudo systemctl restart newsbot

# Pull updates from GitHub and restart
cd /home/newsbot && git pull && sudo systemctl restart newsbot
```

## Environment

Secrets go in `.env`:
```
BOT_TOKEN=...
CHANNEL_ID=...
```

Runtime: Python 3.12.7. Dependencies: `pip install -r requirements.txt`. The `sentence-transformers` model (`paraphrase-multilingual-mpnet-base-v2`) is downloaded on first run and cached in `~/.cache/`.

## Architecture

```
bot.py              — entry point: scheduler loop, filters, sends Telegram messages
config.py           — all tuneable parameters and site definitions (SITES, thresholds, filters)
scraper.py          — fetches news from all sites (RSS via feedparser, HTML via requests+BS4)
duplicate_checker.py — detects duplicate news using TF-IDF or sentence-transformers
url_filter.py       — filters out unwanted categories by URL pattern or breadcrumb sections
storage.py          — persists sent URLs to sent_urls.json
```

### Data flow

1. `scrape_all_sites()` collects news items from all `SITES` in `config.py`
2. `filter_and_sort()` drops items older than `NEWS_MAX_AGE_MINUTES` and sorts oldest-first
3. `is_filtered()` drops items matching URL patterns (`URL_FILTERS`) or section breadcrumbs (`SECTION_FILTERS`)
4. `is_duplicate()` compares the new item against `news_history.json` (last N hours) using cosine similarity
5. Items that pass all checks are sent via `send_with_retry()` and saved to both `sent_urls.json` and `news_history.json`

### Day/Night modes

The scheduler interval and news age window change automatically based on Riga time (01:00–07:00 = night). After each run, the job is rescheduled with the current mode's interval.

### Adding a new news source

Add an entry to `SITES` in `config.py`. Two types:
- `"type": "rss"` — feedparser reads the RSS URL; set `tz_offset` if the feed's timezone is wrong
- `"type": "scrape"` — CSS selector-based HTML scraping; set `fetch_paragraph: False` if the site blocks article requests

To filter categories for a new source, add URL patterns to `URL_FILTERS` or section paths to `SECTION_FILTERS`.

### Duplicate detection

Configured by `DUPLICATE_METHOD` in `config.py`:
- `"sentence_transformers"` — semantic similarity, recommended (threshold ~0.75). The model is a lazy singleton loaded on first call.
- `"tfidf"` — faster, no GPU needed, less accurate (threshold ~0.6)

The "Ранее по теме" (related news) feature links to a previously sent message when similarity falls in the range `[SIMILARITY_THRESHOLD - BELOW, SIMILARITY_THRESHOLD + ABOVE]` — partial matches that aren't full duplicates.

### Persistent state files (git-ignored)

- `sent_urls.json` — set of all URLs ever sent; prevents re-sending across restarts
- `news_history.json` — recent published items with embeddings metadata; used for duplicate detection window

## Known issues

### rus.lsm.lv — Cloudflare block (HTTP 403)

`rus.lsm.lv` is inaccessible from this VPS. Cloudflare blocks requests from Hetzner datacenter IPs with a challenge response (`cf-mitigated: challenge`, HTTP 403). The site works fine from a residential IP (e.g. home connection).

Possible solutions:
- **Whitelist request** — ask LSM to whitelist the VPS IP via their Cloudflare settings.
- **Residential proxy** — route requests to `rus.lsm.lv` through a residential proxy service.
- **Alternative source** — find another feed covering the same content (e.g. an aggregator that republishes LSM material).
