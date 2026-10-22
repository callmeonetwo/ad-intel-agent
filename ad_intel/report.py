"""Step 6: Claude Sonnet turns the stats into findings and recommendations;
this module renders them to Markdown and a self-contained HTML page with charts."""
import csv
import html
import json
from typing import Literal

from pydantic import BaseModel, Field

from .config import REPORT_MODEL, REPORTS, anthropic_client


class Finding(BaseModel):
    title: str
    explanation: str = Field(description="2-3 plain-language sentences for a marketer")
    evidence: str = Field(description="The exact numbers from the stats that support it")


class BrandNote(BaseModel):
    brand: str
    positioning: str = Field(description="How this advertiser sells, one sentence")


class Recommendation(BaseModel):
    title: str
    what_to_make: str = Field(description="Concrete creative to produce: format, length, structure")
    why: str = Field(description="Evidence from the data, with numbers")
    example_hook: str = Field(description="A sample opening line written for the client")
    priority: Literal["start now", "test", "later"]


class Report(BaseModel):
    headline: str = Field(description="One sentence: the single most useful takeaway")
    summary: list[str] = Field(description="3 short bullets for a busy reader")
    findings: list[Finding] = Field(description="4 to 6 findings")
    brand_map: list[BrandNote] = Field(description="Up to 8 advertisers, most relevant first")
    gaps: list[str] = Field(description="Underused formats, hooks or angles: 2 to 4 items")
    recommendations: list[Recommendation] = Field(description="5 to 7 recommendations")
    caveats: list[str] = Field(description="2 to 4 honest limits of this data")


SYSTEM = """You are a senior creative strategist writing a competitor ad & reels report for a client.
Rules:
- Use ONLY numbers present in the stats JSON. Never invent a metric, CTR, ROAS or spend.
- Days live is a proxy for profitability (advertisers switch off losing ads), not proof. Say "likely" where needed.
- Every ad in the snapshot is STILL RUNNING. A short days-live number means the ad is newer, not that it failed.
  Never call a format or tactic "weak" because its ads are newer; at most say it is "newer / not yet proven".
- Segments: "brand" = direct competitors; "marketplace" = automated catalog sellers; "off_niche" = B2B suppliers,
  menswear or accessories that the keyword search also returned. Base conclusions on "brand"; mention the rest briefly.
- Marketplaces (e.g. SHEIN, Alibaba) run automated catalog ads; analyse them separately from brands.
- Small groups (n < 5) are directional only; say so.
- Plain English, short sentences, no jargon without a quick explanation. No guarantees of results.
- Recommendations must be things the client's creative team can brief tomorrow."""


def write_report(niche_key: str, niche: dict, stats: dict) -> tuple[Report, dict]:
    client = anthropic_client()
    prompt = (f"Niche: {niche['title']}\nClient: {niche['client_brief']}\n"
              f"Data snapshot date: {stats['snapshot']}\n\nStats JSON:\n"
              + json.dumps(stats, ensure_ascii=False, default=str))
    resp = client.messages.parse(
        model=REPORT_MODEL,
        max_tokens=16000,
        system=SYSTEM,
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": prompt}],
        output_format=Report,
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise RuntimeError(f"report failed: stop_reason={resp.stop_reason}")
    usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
    return resp.parsed_output, usage


# ---------- rendering ----------

def export_table(niche_key: str, creatives: list[dict]) -> str:
    path = REPORTS / f"{niche_key}_creatives.csv"
    cols = ["kind", "brand", "segment", "format", "days_live", "views", "views_vs_median", "start", "url",
            "hook_type", "hook_text", "main_promise", "angle", "emotion", "creative_format",
            "social_proof", "social_proof_text", "urgency", "offer", "cta", "is_template_copy", "text"]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for c in creatives:
            row = {**c, **(c.get("label") or {})}
            row["text"] = (c["text"] or "").replace("\n", " ")[:500]
            w.writerow(row)
    return path.name


def _bars(title: str, rows: list[tuple[str, float]], unit: str = "", note: str = "") -> str:
    """Horizontal bar chart as inline SVG, values labelled at the bar end."""
    rows = [r for r in rows if r[1] is not None][:10]
    if not rows:
        return ""
    peak = max(v for _, v in rows) or 1
    row_h, label_w, bar_w = 26, 170, 330
    h = row_h * len(rows) + 8
    parts = [f'<svg viewBox="0 0 {label_w + bar_w + 70} {h}" role="img" aria-label="{html.escape(title)}">']
    for i, (label, v) in enumerate(rows):
        y = i * row_h + 4
        w = max(2, bar_w * v / peak)
        val = f"{v:,.0f}{unit}" if isinstance(v, (int, float)) and v >= 10 else f"{v}{unit}"
        parts.append(
            f'<text x="{label_w - 8}" y="{y + 15}" text-anchor="end" class="lbl">{html.escape(str(label))[:26]}</text>'
            f'<rect x="{label_w}" y="{y + 3}" width="{w:.1f}" height="16" rx="3" class="bar"/>'
            f'<text x="{label_w + w + 6}" y="{y + 15}" class="val">{val}</text>')
    parts.append("</svg>")
    note_html = f'<p class="note">{html.escape(note)}</p>' if note else ""
    return f'<figure><figcaption>{html.escape(title)}</figcaption>{"".join(parts)}{note_html}</figure>'


def _charts(stats: dict) -> list[str]:
    a = stats["ads"]
    charts = [
        _bars("Ad formats used by brands (number of ads)", list(a["display_format_brand"].items()),
              note="DPA = catalog ads from a product feed; DCO = dynamic creative, Meta mixes images and texts."),
        _bars("Hook types in brand ads (number of ads)", list(a["hook_type_brand"].items())),
        _bars("Median days live by hook type (brand ads, groups of 2+)",
              [(f"{r['group']} (n={r['n']})", r["median"]) for r in a["median_days_by_hook"]], unit=" d",
              note="Longer-running ads are more likely to be profitable. Small groups are directional."),
    ]
    r = stats.get("reels")
    if r:
        charts.append(_bars("Reel views vs account median (x times)",
                            [(f"{x['account']} {x['date']}", x["views_vs_median"]) for x in r["reels"]], unit="x",
                            note=f"Brand median: {r['median_views']:,.0f} views. A creator collab is compared to the brand median."))
    return [c for c in charts if c]


def render(niche_key: str, niche: dict, stats: dict, rep: Report, csv_name: str, cost: dict) -> tuple[str, str]:
    a = stats["ads"]
    t = a["totals"]
    md = [f"# {niche['title']}: competitor creative report", "",
          f"*Snapshot {stats['snapshot']} · {t['ads']} active ads from {t['brands']} advertisers"
          + (f" · {stats['reels']['brand_reels']} brand reels" if stats.get("reels") else "")
          + f" · built by Ad Intel Agent*", "", f"**{rep.headline}**", ""]
    md += [f"- {s}" for s in rep.summary] + ["", "## Key findings", ""]
    for i, f in enumerate(rep.findings, 1):
        md += [f"### {i}. {f.title}", f.explanation, f"", f"*Evidence:* {f.evidence}", ""]
    md += ["## Who sells how", ""] + [f"- **{b.brand}**: {b.positioning}" for b in rep.brand_map]
    md += ["", "## Gaps nobody is using well", ""] + [f"- {g}" for g in rep.gaps]
    md += ["", "## Recommendations: what to make next", ""]
    for i, r in enumerate(rep.recommendations, 1):
        md += [f"### {i}. {r.title} ({r.priority})", f"**Make:** {r.what_to_make}", "",
               f"**Why:** {r.why}", "", f"**Example hook:** \"{r.example_hook}\"", ""]
    md += ["## Longest-running brand ads", "", "| Brand | Format | Days live | Hook | Angle | Copy |", "|---|---|---|---|---|---|"]
    for e in a["longest_running_examples"][:6]:
        copy = (e["text"] or e["headline"] or "").replace("\n", " ").replace("|", "/")[:110]
        md.append(f"| [{e['brand']}]({e['url']}) | {e['format']} | {e['days_live']} | {e['hook_type']} | {e['angle']} | {copy} |")
    if stats.get("reels"):
        md += ["", "## Reels", "", "| Account | Date | Views | vs median | Length | Audio | Caption |", "|---|---|---|---|---|---|---|"]
        for x in stats["reels"]["reels"]:
            md.append(f"| [{x['account']}]({x['url']}) | {x['date']} | {x['views']:,} | {x['views_vs_median']}x | "
                      f"{x['duration_s']}s | {x['audio']} | {x['caption'][:70].replace(chr(10), ' ').replace('|', '/')} |")
    if stats.get("vs_previous"):
        p = stats["vs_previous"]
        md += ["", f"## Change since {p['previous_snapshot']}", "",
               f"- Ads: {p['ads_change']:+d}", f"- New advertisers: {', '.join(p['new_brands']) or 'none'}",
               f"- Advertisers gone: {', '.join(p['gone_brands']) or 'none'}"]
    md += ["", "## Limits of this data", ""] + [f"- {c}" for c in rep.caveats]
    md += ["", "## Method", "",
           "Apify collected public ads from the Meta Ad Library and public reels from Instagram. "
           f"Claude Haiku tagged every creative (hook, promise, angle, emotion, format, proof, urgency, offer, CTA) as JSON; "
           f"Claude Sonnet wrote the findings from counted statistics only. Full tagged table: `{csv_name}`. "
           f"Model usage for this run: {cost['summary']}."]
    md_text = "\n".join(md) + "\n"

    e = html.escape
    h = []
    h.append(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(niche['title'])} · Ad Intel</title>
<style>{CSS}</style></head><body><main>
<p class="eyebrow">Ad Intel Agent · competitor creative report</p>
<h1>{e(niche['title'])}</h1>
<p class="meta">Snapshot {e(stats['snapshot'])} · {t['ads']} active ads · {t['brands']} advertisers · {t['winners_90d']} brand ads live 90+ days
{f" · {stats['reels']['brand_reels']} brand reels" if stats.get('reels') else ''}</p>
<p class="headline">{e(rep.headline)}</p>
<ul class="summary">{''.join(f'<li>{e(s)}</li>' for s in rep.summary)}</ul>
<section class="kpis">
 <div><b>{t['brand_ads']}</b><span>brand ads</span></div>
 <div><b>{t['marketplace_ads']}</b><span>marketplace ads</span></div>
 <div><b>{a['totals']['median_days_live_brand']:.0f} d</b><span>median days live (brands)</span></div>
 <div><b>{a['social_proof_share_brand']}%</b><span>brand ads with social proof</span></div>
</section>
<h2>Key findings</h2>""")
    for i, f in enumerate(rep.findings, 1):
        h.append(f'<div class="card"><h3>{i}. {e(f.title)}</h3><p>{e(f.explanation)}</p><p class="ev">{e(f.evidence)}</p></div>')
    h.append('<h2>Charts</h2><div class="charts">' + "".join(_charts(stats)) + "</div>")
    h.append("<h2>Who sells how</h2><dl class=\"brands\">" + "".join(
        f"<dt>{e(b.brand)}</dt><dd>{e(b.positioning)}</dd>" for b in rep.brand_map) + "</dl>")
    h.append("<h2>Gaps nobody is using well</h2><ul>" + "".join(f"<li>{e(g)}</li>" for g in rep.gaps) + "</ul>")
    h.append("<h2>Recommendations: what to make next</h2>")
    for i, r in enumerate(rep.recommendations, 1):
        h.append(f'<div class="card rec"><span class="tag">{e(r.priority)}</span><h3>{i}. {e(r.title)}</h3>'
                 f'<p><b>Make:</b> {e(r.what_to_make)}</p><p><b>Why:</b> {e(r.why)}</p>'
                 f'<p class="hook">“{e(r.example_hook)}”</p></div>')
    h.append('<h2>Longest-running brand ads</h2><div class="tw"><table><tr><th>Brand</th><th>Format</th><th>Days</th><th>Hook</th><th>Angle</th><th>Copy</th></tr>')
    for x in a["longest_running_examples"][:6]:
        copy = (x["text"] or x["headline"] or "")[:160]
        h.append(f'<tr><td><a href="{e(x["url"])}">{e(x["brand"])}</a></td><td>{e(x["format"])}</td><td>{x["days_live"]}</td>'
                 f'<td>{e(x["hook_type"])}</td><td>{e(x["angle"])}</td><td class="copy">{e(copy)}</td></tr>')
    h.append("</table></div>")
    if stats.get("reels"):
        rr = stats["reels"]
        h.append('<h2>Reels</h2><div class="tw"><table><tr><th>Account</th><th>Date</th><th>Views</th><th>vs median</th><th>Length</th><th>Audio</th><th>Caption</th></tr>')
        for x in rr["reels"]:
            h.append(f'<tr><td><a href="{e(x["url"])}">{e(x["account"])}</a></td><td>{x["date"]}</td><td>{x["views"]:,}</td>'
                     f'<td>{x["views_vs_median"]}x</td><td>{x["duration_s"]}s</td><td>{e(x["audio"])}</td><td class="copy">{e(x["caption"][:120])}</td></tr>')
        h.append("</table></div>")
    if stats.get("vs_previous"):
        p = stats["vs_previous"]
        h.append(f"<h2>Change since {e(p['previous_snapshot'])}</h2><ul><li>Ads: {p['ads_change']:+d}</li>"
                 f"<li>New advertisers: {e(', '.join(p['new_brands']) or 'none')}</li>"
                 f"<li>Advertisers gone: {e(', '.join(p['gone_brands']) or 'none')}</li></ul>")
    h.append("<h2>Limits of this data</h2><ul>" + "".join(f"<li>{e(c)}</li>" for c in rep.caveats) + "</ul>")
    h.append(f"""<h2>Method</h2><p class="method">Apify collected public ads from the Meta Ad Library and public reels from Instagram.
Claude Haiku tagged every creative (hook, promise, angle, emotion, format, proof, urgency, offer, CTA) as structured JSON;
Claude Sonnet wrote findings from counted statistics only. Full tagged table: <a href="{e(csv_name)}">{e(csv_name)}</a>.
Model usage for this run: {e(cost['summary'])}.</p>
</main></body></html>""")
    html_text = "\n".join(h)

    (REPORTS / f"{niche_key}.md").write_text(md_text, encoding="utf-8")
    (REPORTS / f"{niche_key}.html").write_text(html_text, encoding="utf-8")
    return f"reports/{niche_key}.md", f"reports/{niche_key}.html"


CSS = """
:root{--bg:#fbfaf7;--ink:#1b1b1f;--muted:#5d5d66;--line:#e4e1d8;--card:#fff;--accent:#0f6e6e;--bar:#2a8a8a;--tag:#e6f2f1}
@media (prefers-color-scheme:dark){:root{--bg:#141517;--ink:#ececef;--muted:#a3a3ad;--line:#2c2e33;--card:#1c1d21;--accent:#5cc2c0;--bar:#3fa3a1;--tag:#1f3534}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:880px;margin:0 auto;padding:40px 16px 80px}
.eyebrow{color:var(--accent);font-weight:600;font-size:13px;letter-spacing:.06em;text-transform:uppercase;margin:0}
h1{font-size:32px;line-height:1.2;margin:6px 0 4px}h2{font-size:21px;margin:40px 0 12px;padding-top:12px;border-top:1px solid var(--line)}
h3{font-size:17px;margin:0 0 6px}.meta{color:var(--muted);font-size:14px;margin:0 0 20px}
.headline{font-size:20px;font-weight:600;line-height:1.4;border-left:4px solid var(--accent);padding-left:14px}
.summary li{margin:4px 0}.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:24px 0}
.kpis div{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.kpis b{display:block;font-size:24px;font-variant-numeric:tabular-nums}.kpis span{color:var(--muted);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:10px 0}
.card p{margin:6px 0}.ev{color:var(--muted);font-size:14px}.rec{position:relative}
.tag{float:right;background:var(--tag);color:var(--accent);font-size:12px;font-weight:600;border-radius:99px;padding:2px 10px}
.hook{font-style:italic;color:var(--accent)}figure{margin:0 0 22px}figcaption{font-weight:600;font-size:14px;margin-bottom:6px}
svg{width:100%;height:auto}.lbl,.val{font-size:12px;fill:var(--ink)}.val{fill:var(--muted)}.bar{fill:var(--bar)}
.note{color:var(--muted);font-size:13px;margin:2px 0 0}dl.brands dt{font-weight:600;margin-top:10px}dl.brands dd{margin:2px 0 0;color:var(--muted)}
.tw{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600}td.copy{min-width:240px;color:var(--muted)}a{color:var(--accent)}.method{color:var(--muted);font-size:14px}
"""
