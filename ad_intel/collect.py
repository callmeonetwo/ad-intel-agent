"""Step 1-2: collect ads (Meta Ad Library) and reels (Instagram) through Apify.

Only public data is requested. Comment authors are never stored.
"""
import json
import os
import urllib.request

from .config import ROOT, load_env, write_jsonl

APIFY = "https://api.apify.com/v2"
ADS_ACTOR = "automation-lab~facebook-ads-library"
REELS_ACTOR = "apify~instagram-reel-scraper"

AD_FIELDS = [
    "adArchiveId", "pageName", "pageLikeCount", "isActive", "startDate", "endDate", "platforms",
    "bodyText", "title", "ctaText", "ctaType", "linkCaption", "linkDescription", "displayFormat",
    "containsAiMedia", "collationCount", "cardsCount",
]
REEL_FIELDS = [
    "id", "shortCode", "url", "caption", "hashtags", "mentions", "commentsCount", "likesCount",
    "videoPlayCount", "timestamp", "ownerUsername", "videoDuration", "paidPartnership",
]


def _token() -> str:
    load_env()
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise SystemExit("APIFY_TOKEN is missing in .env (needed only for --collect).")
    return token


def _post(url: str, payload: dict) -> list[dict]:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=900) as resp:
        return json.loads(resp.read())


def _get(url: str) -> list[dict]:
    with urllib.request.urlopen(url, timeout=300) as resp:
        return json.loads(resp.read())


def run_actor(actor: str, payload: dict) -> list[dict]:
    return _post(f"{APIFY}/acts/{actor}/run-sync-get-dataset-items?token={_token()}&clean=true", payload)


def fetch_dataset(dataset_id: str) -> list[dict]:
    return _get(f"{APIFY}/datasets/{dataset_id}/items?token={_token()}&clean=true&format=json")


def _slim_reel(item: dict) -> dict:
    if item.get("error"):
        return {k: item.get(k) for k in ("username", "error", "errorDescription")}
    out = {k: item.get(k) for k in REEL_FIELDS}
    music = item.get("musicInfo") or {}
    out["music"] = {k: music.get(k) for k in ("artist_name", "song_name", "uses_original_audio")}
    return out


def collect(niche: dict, fresh: bool) -> None:
    """fresh=True runs the scrapers again; otherwise re-downloads the stored Apify datasets."""
    ads_cfg = niche["ads"]
    if fresh:
        ads = run_actor(ADS_ACTOR, {
            "searchQueries": ads_cfg["search_queries"],
            "pageUrls": ads_cfg["page_urls"],
            "country": niche["country"],
            "activeStatus": "active",
            "maxAds": ads_cfg["max_ads"],
        })
    else:
        ads = fetch_dataset(ads_cfg["apify_dataset"])
    write_jsonl(ROOT / ads_cfg["file"], [{k: a.get(k) for k in AD_FIELDS} for a in ads])
    print(f"  ads: {len(ads)} saved to {ads_cfg['file']}")

    reels_cfg = niche.get("reels")
    if not reels_cfg:
        return
    if fresh:
        reels = run_actor(REELS_ACTOR, {
            "username": reels_cfg["usernames"],
            "resultsLimit": reels_cfg["results_limit"],
        })
    else:
        reels = fetch_dataset(reels_cfg["apify_dataset"])
    write_jsonl(ROOT / reels_cfg["file"], [_slim_reel(r) for r in reels])
    print(f"  reels: {len(reels)} saved to {reels_cfg['file']}")
