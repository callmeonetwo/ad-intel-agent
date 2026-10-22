"""Ad Intel Agent: competitor ads + reels -> AI tagging -> patterns -> client-ready report.

    python agent.py                 # all niches from niches.json, using saved data
    python agent.py swimwear_uk     # one niche
    python agent.py --collect       # re-download the stored Apify datasets first
    python agent.py --fresh         # run the Apify scrapers again (costs Apify credits)
"""
import argparse
import json
import sys

from ad_intel import analyze, collect, label, report, score
from ad_intel.config import REPORTS, load_niches

PRICES = {"haiku": (0.10, 0.50), "sonnet": (2.00, 10.00)}  # USD per 1M tokens, input/output


def _cost(u: dict, model: str) -> float:
    pin, pout = PRICES[model]
    return (u["input_tokens"] * pin + u["output_tokens"] * pout) / 1_000_000


def run(key: str, niche: dict, collect_mode: str | None) -> None:
    print(f"\n== {key}: {niche['title']}")
    if collect_mode:
        collect.collect(niche, fresh=(collect_mode == "fresh"))

    ads, snapshot = score.load_ads(niche)
    reels, not_found = score.load_reels(niche)
    print(f"  loaded {len(ads)} ads, {len(reels)} reels (snapshot {snapshot})")

    creatives, label_usage = label.label_all(key, ads + reels)

    stats = {"snapshot": snapshot, "ads": analyze.analyze_ads([c for c in creatives if c["kind"] == "ad"]),
             "reels": analyze.analyze_reels([c for c in creatives if c["kind"] == "reel"], not_found)}
    stats["vs_previous"] = analyze.compare_with_previous(key, snapshot, stats)
    (REPORTS / f"{key}_stats.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False, default=str),
                                                encoding="utf-8")

    rep, report_usage = report.write_report(key, niche, stats)
    labels_total = label_usage["total"]
    cost = {"summary": (f"labeling {len(creatives)} creatives with Haiku: {labels_total['calls']} calls, "
                        f"${_cost(labels_total, 'haiku'):.3f} (cached after the first run); "
                        f"report with Sonnet: ${_cost(report_usage, 'sonnet'):.3f}")}

    csv_name = report.export_table(key, creatives)
    md, html_path = report.render(key, niche, stats, rep, csv_name, cost)
    print(f"  report: {html_path} and {md}  ({cost['summary']})")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("niches", nargs="*", help="niche keys from niches.json (default: all)")
    p.add_argument("--collect", action="store_true", help="re-download saved Apify datasets")
    p.add_argument("--fresh", action="store_true", help="run Apify scrapers again")
    args = p.parse_args()

    niches = load_niches()
    keys = args.niches or list(niches)
    mode = "fresh" if args.fresh else "dataset" if args.collect else None
    for key in keys:
        if key not in niches:
            raise SystemExit(f"Unknown niche '{key}'. Known: {', '.join(niches)}")
        run(key, niches[key], mode)


if __name__ == "__main__":
    main()
