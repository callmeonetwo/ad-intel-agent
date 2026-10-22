"""Step 5: find patterns. Pure counting, no LLM, so every number in the report is traceable."""
import json
from collections import Counter, defaultdict
from statistics import median

from .config import DATA

WINNER_DAYS = 90  # an ad live for a quarter is treated as a likely winner


def _share(items, pred) -> float:
    items = list(items)
    return round(100 * sum(1 for i in items if pred(i)) / len(items), 1) if items else 0.0


def _dist(items, key) -> list[tuple[str, int]]:
    return Counter(key(i) for i in items).most_common()


def _median_by(items, key, value, min_n=2) -> list[dict]:
    groups = defaultdict(list)
    for i in items:
        groups[key(i)].append(value(i))
    rows = [{"group": g, "n": len(v), "median": round(median(v))} for g, v in groups.items() if len(v) >= min_n]
    return sorted(rows, key=lambda r: -r["median"])


def _lift(items, winners, feature_name, pred) -> dict:
    # Every ad in the snapshot is still running, so the comparison group is "newer", not "failed".
    newer = [i for i in items if i not in winners]
    return {"feature": feature_name, "share_in_live_90d_plus": _share(winners, pred),
            "share_in_newer_still_running": _share(newer, pred), "n_live_90d_plus": len(winners),
            "n_newer": len(newer)}


def analyze_ads(ads: list[dict]) -> dict:
    labeled = [a for a in ads if a.get("label")]
    brands = [a for a in labeled if a["segment"] == "brand"]
    L = lambda a: a["label"]
    winners = [a for a in brands if a["days_live"] >= WINNER_DAYS]

    unique = {}
    for a in brands:
        unique.setdefault(a["sig"], a)

    groups = defaultdict(list)
    for a in labeled:
        groups[a["brand"]].append(a)
    per_brand = []
    for brand, group in groups.items():
        per_brand.append({
            "brand": brand,
            "segment": group[0]["segment"],
            "ads": len(group),
            "unique_copies": len({a["sig"] for a in group}),
            "median_days_live": median(a["days_live"] for a in group),
            "max_days_live": max(a["days_live"] for a in group),
            "formats": dict(_dist(group, lambda a: a["format"])),
            "hooks": dict(_dist(group, lambda a: L(a)["hook_type"])),
            "angles": [x for x, _ in _dist(group, lambda a: L(a)["angle"].lower())[:3]],
            "offers": dict(_dist(group, lambda a: L(a)["offer"])),
            "social_proof_share": _share(group, lambda a: L(a)["social_proof"]),
            "template_copy_share": _share(group, lambda a: L(a)["is_template_copy"]),
        })
    per_brand.sort(key=lambda b: -b["ads"])

    examples = sorted(unique.values(), key=lambda a: -a["days_live"])[:10]

    return {
        "totals": {
            "ads": len(ads),
            "labeled": len(labeled),
            "brand_ads": len(brands),
            "marketplace_ads": sum(1 for a in labeled if a["segment"] == "marketplace"),
            "off_niche_ads": sum(1 for a in labeled if a["segment"] == "off_niche"),
            "all_ads_still_active": all(a["active"] for a in ads),
            "brands": len({a["brand"] for a in labeled}),
            "unique_brand_copies": len(unique),
            "winners_90d": len(winners),
            "median_days_live_brand": median(a["days_live"] for a in brands) if brands else None,
        },
        "segments": dict(_dist(labeled, lambda a: a["segment"])),
        "display_format_all": dict(_dist(labeled, lambda a: a["format"])),
        "display_format_brand": dict(_dist(brands, lambda a: a["format"])),
        "creative_format_brand": dict(_dist(brands, lambda a: L(a)["creative_format"])),
        "hook_type_brand": dict(_dist(brands, lambda a: L(a)["hook_type"])),
        "offer_brand": dict(_dist(brands, lambda a: L(a)["offer"])),
        "emotion_brand": dict(_dist(brands, lambda a: L(a)["emotion"])),
        "cta_brand": dict(_dist(brands, lambda a: L(a)["cta"])),
        "angles_brand": _dist(brands, lambda a: L(a)["angle"].lower())[:12],
        "longevity_brand": dict(_dist(brands, lambda a: a["longevity"])),
        "social_proof_share_brand": _share(brands, lambda a: L(a)["social_proof"]),
        "urgency_share_brand": _share(brands, lambda a: L(a)["urgency"]),
        "template_copy_share_marketplace": _share([a for a in labeled if a["segment"] == "marketplace"],
                                                  lambda a: L(a)["is_template_copy"]),
        "median_days_by_display_format": _median_by(brands, lambda a: a["format"], lambda a: a["days_live"]),
        "median_days_by_hook": _median_by(brands, lambda a: L(a)["hook_type"], lambda a: a["days_live"]),
        "median_days_by_creative_format": _median_by(brands, lambda a: L(a)["creative_format"], lambda a: a["days_live"]),
        "median_days_by_offer": _median_by(brands, lambda a: L(a)["offer"], lambda a: a["days_live"]),
        "long_runners_vs_newer": [
            _lift(brands, winners, "social proof", lambda a: L(a)["social_proof"]),
            _lift(brands, winners, "urgency", lambda a: L(a)["urgency"]),
            _lift(brands, winners, "any offer", lambda a: L(a)["offer"] != "none"),
            _lift(brands, winners, "video format", lambda a: a["format"] == "VIDEO"),
            _lift(brands, winners, "catalog/DPA format", lambda a: a["format"] == "DPA"),
            _lift(brands, winners, "dynamic creative (DCO)", lambda a: a["format"] == "DCO"),
            _lift(brands, winners, "template copy", lambda a: L(a)["is_template_copy"]),
        ],
        "per_brand": per_brand,
        "longest_running_examples": [_example(a) for a in examples],
    }


def _example(a: dict) -> dict:
    return {
        "brand": a["brand"], "format": a["format"], "days_live": a["days_live"], "start": a["start"],
        "url": a["url"], "headline": a.get("headline"), "text": a["text"][:400],
        "hook_type": a["label"]["hook_type"], "angle": a["label"]["angle"],
        "main_promise": a["label"]["main_promise"], "offer": a["label"]["offer"],
        "social_proof": a["label"]["social_proof_text"],
    }


def analyze_reels(reels: list[dict], not_found: list[str]) -> dict | None:
    if not reels:
        return None
    brand = [r for r in reels if r["segment"] == "brand"]
    views = [r["views"] for r in brand]
    L = lambda r: r["label"] or {}
    short = [r for r in brand if r["duration_s"] < 15]
    mid = [r for r in brand if 15 <= r["duration_s"] < 20]
    long = [r for r in brand if r["duration_s"] >= 20]
    bucket = lambda g: {"n": len(g), "median_views": round(median(r["views"] for r in g)) if g else None}
    promo = [r for r in brand if L(r).get("offer") not in (None, "none")]
    no_promo = [r for r in brand if L(r).get("offer") in (None, "none")]
    licensed = [r for r in brand if not r["original_audio"]]
    original = [r for r in brand if r["original_audio"]]
    ranked = sorted(reels, key=lambda r: -r["views"])
    tags = Counter(t for r in brand for t in (r["extra"]["hashtags"] or []))
    top_tag = tags.most_common(1)[0][0] if tags else None
    return {
        "accounts_not_found": not_found,
        "brand_reels": len(brand),
        "collab_reels": len(reels) - len(brand),
        "median_views": round(median(views)),
        "max_views": max(views),
        "min_views": min(views),
        "median_engagement_rate": median(r["engagement_rate"] for r in brand if r["engagement_rate"] is not None),
        "median_duration_s": round(median(r["duration_s"] for r in brand), 1),
        "original_audio_share": _share(brand, lambda r: r["original_audio"]),
        "views_by_duration": {"<15s": bucket(short), "15-20s": bucket(mid), "20s+": bucket(long)},
        "views_by_audio": {"original": bucket(original), "licensed": bucket(licensed)},
        "views_by_promo_caption": {"promo/offer in caption": bucket(promo), "no offer": bucket(no_promo)},
        "top_hashtag": top_tag,
        "top_hashtag_share": _share(brand, lambda r: top_tag in (r["extra"]["hashtags"] or [])),
        "reels": [{
            "account": r["brand"], "segment": r["segment"], "url": r["url"], "date": r["start"],
            "views": r["views"], "views_vs_median": r["views_vs_median"], "likes": r["likes"],
            "comments": r["comments"], "engagement_rate": r["engagement_rate"],
            "duration_s": r["duration_s"], "audio": r["extra"]["audio"], "caption": r["text"][:200],
            "hook_type": L(r).get("hook_type"), "angle": L(r).get("angle"), "offer": L(r).get("offer"),
        } for r in ranked],
    }


def compare_with_previous(niche_key: str, snapshot: str, stats: dict) -> dict | None:
    """Store this run and diff it against the previous one (weekly monitoring)."""
    hist = DATA / "history" / niche_key
    hist.mkdir(parents=True, exist_ok=True)
    slim = {
        "snapshot": snapshot,
        "totals": stats["ads"]["totals"],
        "brands": {b["brand"]: b["ads"] for b in stats["ads"]["per_brand"]},
        "display_format_brand": stats["ads"]["display_format_brand"],
        "hook_type_brand": stats["ads"]["hook_type_brand"],
    }
    previous = sorted(p for p in hist.glob("*.json") if p.stem < snapshot)
    (hist / f"{snapshot}.json").write_text(json.dumps(slim, indent=1), encoding="utf-8")
    if not previous:
        return None
    prev = json.loads(previous[-1].read_text(encoding="utf-8"))
    return {
        "previous_snapshot": prev["snapshot"],
        "new_brands": sorted(set(slim["brands"]) - set(prev["brands"])),
        "gone_brands": sorted(set(prev["brands"]) - set(slim["brands"])),
        "ads_change": slim["totals"]["ads"] - prev["totals"]["ads"],
        "format_change": {k: slim["display_format_brand"].get(k, 0) - prev["display_format_brand"].get(k, 0)
                          for k in set(slim["display_format_brand"]) | set(prev["display_format_brand"])},
        "hook_change": {k: slim["hook_type_brand"].get(k, 0) - prev["hook_type_brand"].get(k, 0)
                        for k in set(slim["hook_type_brand"]) | set(prev["hook_type_brand"])},
    }
