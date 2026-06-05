#!/usr/bin/env python3
"""Turn a Telegram Desktop JSON export into clean, per-topic documents for RAG.

Telegram Desktop  ->  ⋮  ->  Export chat history  ->  Format: JSON  ->  result.json

This handles two ways a chat can be organized into "topics":

  1. Native forum topics  -> "topic_created" service messages (some groups).
  2. Pinned-anchor threads -> a flat supergroup where people keep replying to a
     small set of pinned "category" messages (e.g. one for jobs, one for visas).
     We detect these as message ids that accumulate large reply threads.

The Minerva Cross-Class Chat is case (2): it migrated from a group, has no
forum topics, and uses recurring reply anchors like 20442 (jobs), 18137
(course sections), 18128 (visas), 24934, etc.

Pipeline (ingestion prep only — chunk size/overlap stays a Milestone 2 choice):
  1. Resolve each message's thread root (walk reply_to_message_id up).
  2. Treat native topics, or roots with big threads, as "topics" and label them.
  3. Scrub PII: authors -> stable pseudonyms; phone/email/@mention entities ->
     placeholders. URLs from links are preserved (they're core content here).
  4. Skip service/media-only/empty messages.
  5. Segment each topic into conversation blocks on long time gaps.
  6. Write one .txt per topic + manifest.json (rows for planning.md / README.md).

KNOWN LIMITATION: personal *names written in message bodies* (e.g. "ask Ben
Nelson") are not redacted — that needs NER and risks false positives on common
first names. Author handles and contact entities are redacted; document this
residual risk in your planning.md privacy/ethics notes.

Usage:
    python scripts/telegram_export.py --inspect result.json          # run FIRST
    python scripts/telegram_export.py --input result.json --output documents/telegram
    python scripts/telegram_export.py --input result.json --min-thread 15
    python scripts/telegram_export.py --input result.json --no-redact # debugging only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# --- Tunables -----------------------------------------------------------------
DEFAULT_MIN_THREAD = 15      # reply-thread size for a root to count as a "topic"
SEGMENT_GAP_MINUTES = 180    # gap that starts a new conversation block within a topic
MISC_TOPIC = "Misc / Untagged"
TOPIC_CREATE_ACTIONS = {"topic_created"}

# Entity types that carry PII -> replaced with a placeholder when redacting.
REDACT_ENTITY = {
    "email": "[email]",
    "phone": "[phone]",
    "mention": "[handle]",
    "mention_name": "[name]",
}

# Regex fallback for PII inside plain-string text (no typed entities available).
_HANDLE_RE = re.compile(r"@[A-Za-z][A-Za-z0-9_]{3,}")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")


# --- Text extraction + scrubbing ----------------------------------------------
def build_text(message: dict, redact: bool) -> str:
    """Assemble message text. Prefer 'text_entities' (typed) so we can redact
    PII by entity type and preserve link URLs; fall back to the plain string."""
    entities = message.get("text_entities")
    if isinstance(entities, list) and entities:
        parts = []
        for e in entities:
            if not isinstance(e, dict):
                continue
            etype, txt = e.get("type"), e.get("text", "")
            if redact and etype in REDACT_ENTITY:
                parts.append(REDACT_ENTITY[etype])
            elif etype == "text_link" and e.get("href"):
                parts.append(f"{txt} ({e['href']})")  # keep both label and URL
            else:
                parts.append(txt)
        return "".join(parts).strip()

    text = message.get("text", "")
    if isinstance(text, list):  # legacy list form without typed entities
        text = "".join(p if isinstance(p, str) else p.get("text", "") for p in text)
    text = (text or "").strip()
    if redact and text:
        text = _EMAIL_RE.sub("[email]", text)
        text = _PHONE_RE.sub("[phone]", text)
        text = _HANDLE_RE.sub("[handle]", text)
    return text


def pseudonym(from_id, from_name: str) -> str:
    """Stable, non-reversible alias so one person stays consistent across messages
    without exposing identity."""
    seed = str(from_id) if from_id not in (None, "") else (from_name or "unknown")
    return f"User_{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:6]}"


# --- Thread / topic resolution ------------------------------------------------
def native_topics(messages: list[dict]) -> dict[int, str]:
    """{id: title} from forum 'topic_created' service messages (empty for most)."""
    return {
        m["id"]: m["title"]
        for m in messages
        if m.get("type") == "service"
        and m.get("action") in TOPIC_CREATE_ACTIONS
        and m.get("title")
    }


def build_root_resolver(messages: list[dict]):
    """Return (find_root, by_id). find_root(id) walks reply_to_message_id up to the
    thread's ultimate ancestor — even if that anchor message was not exported
    (deleted), so replies to a missing anchor still group together by its id."""
    by_id = {m["id"]: m for m in messages if "id" in m}
    parent_of = {
        m["id"]: m.get("reply_to_message_id")
        for m in messages
        if m.get("type") == "message" and "id" in m
    }
    cache: dict[int, int] = {}

    def find_root(mid: int) -> int:
        if mid in cache:
            return cache[mid]
        seen, cur = [], mid
        while cur in parent_of and parent_of[cur] is not None and parent_of[cur] != cur:
            if cur in seen:  # cycle guard
                break
            seen.append(cur)
            cur = parent_of[cur]
        for node in seen:
            cache[node] = cur
        cache[mid] = cur
        return cur

    return find_root, by_id


def clean_label(text: str, fallback: str) -> str:
    """One-line, truncated topic label from an anchor message's text."""
    label = " ".join(text.split())[:60]
    return label or fallback


# --- Conversation segmentation ------------------------------------------------
def parse_date(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def segment(msgs: list[dict], gap_minutes: int) -> list[list[dict]]:
    """Split a topic's chronological messages into conversation blocks whenever
    the gap between consecutive messages exceeds gap_minutes."""
    blocks, current, last = [], [], None
    for m in msgs:
        dt = parse_date(m.get("date", ""))
        if current and last and dt and (dt - last).total_seconds() > gap_minutes * 60:
            blocks.append(current)
            current = []
        current.append(m)
        last = dt or last
    if current:
        blocks.append(current)
    return blocks


def slugify(name: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", name).strip().lower()
    return re.sub(r"[\s_-]+", "-", slug) or "topic"


# --- Main ---------------------------------------------------------------------
def collect(messages, redact):
    """Return content messages with cleaned fields attached, skipping
    service/media-only/empty messages."""
    out = []
    for m in messages:
        if m.get("type") != "message" or "id" not in m:
            continue
        text = build_text(m, redact)
        if not text:  # media-only, stickers, empty
            continue
        m["_text"] = text
        m["_author"] = pseudonym(m.get("from_id"), m.get("from")) if redact else (m.get("from") or "Unknown")
        out.append(m)
    return out


def assign_topics(messages, content, min_thread):
    """Decide the topic label for each content message id."""
    find_root, by_id = build_root_resolver(messages)
    native = native_topics(messages)

    if native:  # forum-style: topics are authoritative
        anchors = dict(native)
    else:       # anchor-thread style: roots with big threads become topics
        sizes = Counter(find_root(m["id"]) for m in content)
        anchors = {}
        for root_id, count in sizes.items():
            if count >= min_thread:
                src = by_id.get(root_id, {})
                anchors[root_id] = clean_label(src.get("_text") or build_text(src, True), f"Thread {root_id}")

    topic_of = {m["id"]: anchors.get(find_root(m["id"]), MISC_TOPIC) for m in content}
    return topic_of, anchors


def render(topic: str, blocks: list[list[dict]]) -> str:
    lines = [f"# Topic: {topic}", ""]
    for i, block in enumerate(blocks, 1):
        lines.append(f"--- Conversation {i} ({block[0].get('date', '?')[:10]}) ---")
        for m in block:
            lines.append(f"{m['_author']}: {m['_text']}")
        lines.append("")
    return "\n".join(lines)


def run(args):
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    messages = data.get("messages", [])
    redact = not args.no_redact

    content = collect(messages, redact)
    topic_of, anchors = assign_topics(messages, content, args.min_thread)

    by_topic: dict[str, list[dict]] = defaultdict(list)
    for m in content:
        by_topic[topic_of[m["id"]]].append(m)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    used, manifest = set(), []
    for topic, msgs in sorted(by_topic.items(), key=lambda kv: -len(kv[1])):
        msgs.sort(key=lambda m: m.get("id", 0))
        blocks = segment(msgs, args.gap)
        slug = slugify(topic)
        while slug in used:
            slug += "-x"
        used.add(slug)
        (out_dir / f"{slug}.txt").write_text(render(topic, blocks), encoding="utf-8")
        manifest.append({"topic": topic, "file": str(out_dir / f"{slug}.txt"),
                         "messages": len(msgs), "conversations": len(blocks)})

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Chat: {data.get('name', '?')}  ({len(messages)} raw messages, {len(content)} with text)")
    print(f"Detected {len(anchors)} topic(s); wrote {len(manifest)} files to {out_dir}/\n")
    print(f"{'Topic':<48}{'Msgs':>7}{'Convos':>8}")
    print("-" * 63)
    for row in manifest:
        print(f"{row['topic'][:47]:<48}{row['messages']:>7}{row['conversations']:>8}")
    print(f"\nManifest: {out_dir / 'manifest.json'}")


def inspect(path):
    """Reveal the real structure so you can confirm field names / pick --min-thread."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    messages = data.get("messages", [])
    print(f"Chat name : {data.get('name', '?')}")
    print(f"Chat type : {data.get('type', '?')}")
    print(f"Messages  : {len(messages)}\n")
    print("Message types  :", dict(Counter(m.get("type") for m in messages)))
    print("Service actions:", dict(Counter(m.get("action") for m in messages if m.get("type") == "service")))

    native = native_topics(messages)
    print(f"\nNative forum topics (topic_created): {len(native)}")
    for tid, title in list(native.items())[:25]:
        print(f"  id={tid}  {title!r}")
    if native:
        return

    find_root, by_id = build_root_resolver(messages)
    content = [m for m in messages if m.get("type") == "message" and "id" in m]
    sizes = Counter(find_root(m["id"]) for m in content)
    print("\nNo native topics -> using anchor-thread detection.")
    print("Top reply anchors (id, thread size, label) — pick --min-thread below this list:\n")
    print(f"  {'id':>8}{'size':>7}  label")
    for root_id, count in sizes.most_common(30):
        src = by_id.get(root_id, {})
        label = clean_label(build_text(src, True), f"(anchor {root_id} not in export)")
        print(f"  {root_id:>8}{count:>7}  {label}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input")
    ap.add_argument("--output", default="documents/telegram")
    ap.add_argument("--inspect", metavar="JSON", help="Print structure summary and exit (run first)")
    ap.add_argument("--min-thread", type=int, default=DEFAULT_MIN_THREAD,
                    help=f"Reply-thread size for a root to count as a topic (default {DEFAULT_MIN_THREAD})")
    ap.add_argument("--gap", type=int, default=SEGMENT_GAP_MINUTES,
                    help=f"Minutes between messages that starts a new conversation block (default {SEGMENT_GAP_MINUTES})")
    ap.add_argument("--no-redact", action="store_true", help="Disable all PII scrubbing (debugging only)")
    args = ap.parse_args()

    if args.inspect:
        inspect(args.inspect)
    elif args.input:
        run(args)
    else:
        ap.error("--input is required (or use --inspect first)")


if __name__ == "__main__":
    main()
