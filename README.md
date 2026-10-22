# Ad Intel Agent

An AI agent that studies competitors' ads and Reels and tells a brand what creatives to make next.

It collects active ads from the Meta Ad Library and Reels from Instagram, has Claude tag every creative,
scores which ones are likely winning, finds the patterns behind them and writes a 2–3 page report with
5–7 recommendations a creative team can brief straight away.

**Example reports (real public data, snapshot 22 Oct 2026):**

| Niche | Data | Report |
|---|---|---|
| Women's swimwear, UK | 60 active ads from 20 advertisers + 14 Triangl Reels | [HTML](reports/swimwear_uk.html) · [Markdown](reports/swimwear_uk.md) · [tagged table](reports/swimwear_uk_creatives.csv) |
| AI tools and apps, US | 120 active ads from 38 advertisers | [HTML](reports/ai_tools_us.html) · [Markdown](reports/ai_tools_us.md) · [tagged table](reports/ai_tools_us_creatives.csv) |

Cost of one full run on both niches: about **$0.13** in Claude API usage (Haiku tagging $0.015, Sonnet reports ~$0.11).

## How it works

```
collect  →  tag  →  score  →  find patterns  →  report
Apify       Claude    days live,   counting only,    Claude Sonnet writes
            Haiku     Reel vs      no LLM, so every  findings + recommendations,
            (JSON)    account      number is         rendered to HTML + Markdown
                      median       traceable         with charts
```

1. **Collect.** `automation-lab/facebook-ads-library` (Meta Ad Library: copy, format, CTA, start date, page)
   and `apify/instagram-reel-scraper` (views, likes, comments, length, audio, caption, hashtags).
2. **Tag.** Claude Haiku labels each creative as structured JSON: hook type, hook text, main promise, angle,
   emotion, creative format, social proof, urgency, offer, CTA, template copy. Identical copies are tagged once
   and cached, so a weekly re-run only pays for new ads.
3. **Score.** Ads: days live. Advertisers switch off ads that lose money, so an ad running for months is likely
   paying back. All ads in a snapshot are still running, so a short run means *newer*, not *failed*.
   Reels: views relative to the account's median.
4. **Find patterns.** Plain counting in Python: formats, hooks, offers and angles; median days live per group;
   what long runners (90+ days) do differently from newer ads; a profile per advertiser. Marketplaces
   (SHEIN, Alibaba) and off-niche advertisers are kept apart from direct competitors.
5. **Report.** Claude Sonnet gets only the counted statistics and must quote numbers from them.
   Output: findings, who sells how, gaps, recommendations with an example hook, limits of the data.
6. **Repeat.** Each run is stored in `data/history/`; the next run adds a "change since last run" section.

## Run it

Requirements: Python 3.10+.

```bash
pip install -r requirements.txt
cp .env.example .env          # then paste your ANTHROPIC_API_KEY (and APIFY_TOKEN if you want fresh data)
python agent.py               # both niches, from the saved data in data/raw
```

Other options:

```bash
python agent.py swimwear_uk   # one niche
python agent.py --collect     # re-download the saved Apify datasets first
python agent.py --fresh       # run the Apify scrapers again (uses Apify credits, about $1–2 for both niches)
```

Add a niche by adding a block to `niches.json`: search keywords or page URLs, country, Instagram usernames,
marketplaces to separate, and a one-line description of the client.

**Weekly schedule.** On macOS/Linux add a cron line, e.g. `0 8 * * 1 cd /path/to/ad-intel-agent && python agent.py --fresh`.
On Windows use Task Scheduler with the same command.

## Files

```
agent.py              entry point
niches.json           what to monitor
ad_intel/collect.py   Apify (Meta Ad Library, Instagram Reels)
ad_intel/label.py     Claude Haiku tagging with a JSON schema, cached
ad_intel/score.py     days live, Reel vs median
ad_intel/analyze.py   pattern counting, history diff
ad_intel/report.py    Claude Sonnet report + HTML/Markdown rendering
data/raw/             collected public data
data/labeled/         tag cache
reports/              reports, tagged tables, stats JSON
index.html            portfolio page that presents this case
```

## Honest limits

- Days live is a proxy for profit. Meta does not publish spend or results for commercial ads in most countries.
- Tags come from ad copy and format metadata. Images and video frames are not analysed yet (next step: Claude vision on thumbnails).
- Samples are small (25 direct-competitor swimwear ads, 14 Reels from one brand). Reports mark small groups as directional.
- Only public data. No personal data of commenters is collected. Findings are not a guarantee of results.

Built by Roman Huber with Claude Code.
