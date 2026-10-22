"""Step 4: turn raw rows into scored creatives.

Ads: days live. An ad that keeps running for months is very likely paying back,
because advertisers switch off losers. This is a proxy, not a measured ROAS.
Reels: views and engagement relative to the median of the same account.
"""
from datetime import date
from statistics import median

from .config import ROOT, read_jsonl


def longevity_bucket(days: int) -> str:
    if days >= 90:
        return "90+ days"
    if days >= 30:
        return "30-89 days"
    return "<30 days"


def load_ads(niche: dict) -> tuple[list[dict], str]:
    rows = read_jsonl(ROOT / niche["ads"]["file"])
    snapshot = max(date.fromisoformat(r["endDate"]) for r in rows if r.get("endDate"))
    marketplaces = set(niche.get("marketplaces", []))
    off_niche = set(niche.get("off_niche", []))
    out = []
    for r in rows:
        start = date.fromisoformat(r["startDate"])
        end = date.fromisoformat(r["endDate"]) if r.get("endDate") else snapshot
        days = (end - start).days
        out.append({
            "kind": "ad",
            "id": r["adArchiveId"],
            "url": f"https://www.facebook.com/ads/library/?id={r['adArchiveId']}",
            "brand": r["pageName"].strip(),
            "segment": ("marketplace" if r["pageName"].strip() in marketplaces
                        else "off_niche" if r["pageName"].strip() in off_niche else "brand"),
            "format": r.get("displayFormat"),
            "text": r.get("bodyText") or "",
            "headline": r.get("title"),
            "cta": r.get("ctaText"),
            "start": r["startDate"],
            "days_live": days,
            "longevity": longevity_bucket(days),
            "active": bool(r.get("isActive")),
            "extra": {"variants": r.get("collationCount"), "cards": r.get("cardsCount"),
                      "platforms": r.get("platforms")},
        })
    return out, snapshot.isoformat()


def load_reels(niche: dict) -> tuple[list[dict], list[str]]:
    cfg = niche.get("reels")
    if not cfg:
        return [], []
    rows = read_jsonl(ROOT / cfg["file"])
    not_found = [r["username"] for r in rows if r.get("error")]
    reels = [r for r in rows if not r.get("error") and r.get("videoPlayCount")]
    medians = {}
    for owner in {r["ownerUsername"] for r in reels}:
        medians[owner] = median(r["videoPlayCount"] for r in reels if r["ownerUsername"] == owner)
    target = set(cfg["usernames"])
    out = []
    for r in reels:
        owner = r["ownerUsername"]
        # A creator's post that lands in a brand's feed is a collab: compare it to the brand median.
        base_owner = owner if owner in target else next(iter(target & set(r.get("mentions") or [])), owner)
        base = medians.get(base_owner) or medians[owner]
        likes = r["likesCount"] if r.get("likesCount", -1) >= 0 else None
        views = r["videoPlayCount"]
        music = r.get("music") or {}
        out.append({
            "kind": "reel",
            "id": r["shortCode"],
            "url": r["url"],
            "brand": owner,
            "segment": "brand" if owner in target else "creator_collab",
            "format": "reel",
            "text": r.get("caption") or "",
            "headline": None,
            "cta": None,
            "start": r["timestamp"][:10],
            "views": views,
            "likes": likes,
            "comments": r.get("commentsCount", 0),
            "engagement_rate": round((likes + r.get("commentsCount", 0)) / views * 100, 2) if likes is not None else None,
            "views_vs_median": round(views / base, 2),
            "duration_s": round(r.get("videoDuration") or 0, 1),
            "original_audio": bool(music.get("uses_original_audio")),
            "extra": {"duration_s": round(r.get("videoDuration") or 0, 1),
                      "audio": "original" if music.get("uses_original_audio") else f"licensed: {music.get('song_name')}",
                      "hashtags": r.get("hashtags")},
        })
    return out, not_found
