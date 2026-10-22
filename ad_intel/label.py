"""Step 3: Claude Haiku tags every creative into structured JSON.

Identical copies (same page + text) are labeled once. Results are cached on disk,
so a weekly re-run only pays for new creatives.
"""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel, Field

from .config import DATA, LABEL_MODEL, anthropic_client

BATCH = 12

HookType = Literal["question", "number", "ugc", "promise", "shock", "benefit_list",
                   "offer", "social_proof", "story", "statement", "none"]
Emotion = Literal["aspiration", "fomo", "curiosity", "trust", "fear", "joy", "pride", "neutral"]
Format = Literal["catalog", "ugc", "product_video", "graphic", "lifestyle_photo",
                 "influencer", "app_demo", "talking_head", "other"]
Cta = Literal["shop", "learn_more", "install", "sign_up", "profile_visit", "other"]


class Label(BaseModel):
    ref: str = Field(description="The ref of the creative, copied exactly")
    hook_type: HookType = Field(description="How the first line grabs attention")
    hook_text: str = Field(description="First line or opening words, max 12 words")
    main_promise: str = Field(description="Core promise to the viewer, max 12 words")
    angle: str = Field(description="Selling angle in 1-3 words, e.g. 'tummy control', 'sustainability', 'time saving'")
    emotion: Emotion
    creative_format: Format = Field(description="Best guess from copy plus format metadata")
    social_proof: bool = Field(description="Mentions customers, numbers of users, reviews, creators or awards")
    social_proof_text: str = Field(description="The proof itself if present, else empty")
    urgency: bool = Field(description="Deadline, scarcity, 'today', 'before they're gone', limited offer")
    offer: Literal["discount", "free_trial", "free_shipping", "giveaway", "lead_magnet", "guarantee", "bnpl", "none"]
    cta: Cta
    is_template_copy: bool = Field(description="Generic catalog text reused across many products")


class LabelBatch(BaseModel):
    labels: list[Label]


SYSTEM = (
    "You are a performance-marketing analyst. You tag competitor ad creatives and Instagram reels "
    "for a creative-strategy report. Work only from the copy and metadata given; images and video "
    "frames are not available, so infer creative_format from the format field and the wording. "
    "Return exactly one label per input ref."
)


def signature(item: dict) -> str:
    raw = json.dumps([item.get("brand"), item.get("text"), item.get("headline")], ensure_ascii=False)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _prompt(items: list[dict]) -> str:
    blocks = []
    for it in items:
        blocks.append(json.dumps({
            "ref": it["sig"], "kind": it["kind"], "brand": it["brand"], "format": it["format"],
            "headline": it.get("headline"), "text": (it.get("text") or "")[:1500],
            "cta_button": it.get("cta"), "extra": it.get("extra"),
        }, ensure_ascii=False))
    return "Tag these creatives:\n" + "\n".join(blocks)


def _label_batch(client, items: list[dict]):
    resp = client.messages.parse(
        model=LABEL_MODEL,
        max_tokens=8000,
        system=SYSTEM,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": _prompt(items)}],
        output_format=LabelBatch,
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise RuntimeError(f"labeling failed: stop_reason={resp.stop_reason}")
    return [l.model_dump() for l in resp.parsed_output.labels], resp.usage


def label_all(niche_key: str, creatives: list[dict]) -> tuple[list[dict], dict]:
    cache_path = DATA / "labeled" / f"{niche_key}_labels.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    for c in creatives:
        c["sig"] = signature(c)
    todo = {c["sig"]: c for c in creatives if c["sig"] not in cache}
    todo_list = list(todo.values())
    batches = [todo_list[i:i + BATCH] for i in range(0, len(todo_list), BATCH)]
    usage = {"input_tokens": 0, "output_tokens": 0, "calls": 0, "new_unique": len(todo_list)}

    if batches:
        client = anthropic_client()
        print(f"  labeling {len(todo_list)} unique creatives with {LABEL_MODEL} in {len(batches)} calls")
        with ThreadPoolExecutor(max_workers=4) as pool:
            for labels, u in pool.map(lambda b: _label_batch(client, b), batches):
                usage["calls"] += 1
                usage["input_tokens"] += u.input_tokens
                usage["output_tokens"] += u.output_tokens
                for l in labels:
                    if l["ref"] in todo:
                        cache[l["ref"]] = l
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")

    # Keep a running total so a cached re-run still reports what the labels cost.
    total_path = DATA / "labeled" / f"{niche_key}_usage.json"
    total = json.loads(total_path.read_text()) if total_path.exists() else {"input_tokens": 0, "output_tokens": 0, "calls": 0}
    for k in total:
        total[k] += usage[k]
    total_path.parent.mkdir(parents=True, exist_ok=True)
    total_path.write_text(json.dumps(total))
    usage["total"] = total

    missing = [c for c in creatives if c["sig"] not in cache]
    if missing:
        print(f"  warning: {len(missing)} creatives came back without a label")
    for c in creatives:
        c["label"] = cache.get(c["sig"])
    return creatives, usage
