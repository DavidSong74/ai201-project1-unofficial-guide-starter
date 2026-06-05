#!/usr/bin/env python3
"""Chunk the per-topic Telegram documents, embed them, and store them in Chroma.

This is Milestone 2 (chunking) + Milestone 3 (embedding + vector store) of the
RAG pipeline. It reads the clean .txt files produced by telegram_export.py.

CHUNKING STRATEGY (data-driven — see the block-size analysis in planning.md):
  The export already segments each topic into "conversation blocks" — reply
  threads cut on long time gaps. A block is a naturally coherent Q&A unit, so
  the chunk unit is the conversation block, NOT a blind fixed-size window:

    * 1 block  -> 1 chunk for ~90% of blocks (median ~315 chars / ~80 tokens).
    * Oversized blocks (> MAX_CHARS) are split on message boundaries with a
      one-message overlap, so a long thread keeps local context across chunks.
    * Tiny blocks (< MIN_CHARS, e.g. "thanks!!") are merged forward into the
      next block in the same topic, so we never embed a lone fragment.

  Each chunk is prefixed with a "Topic: X | date" header so both the embedding
  and the LLM at generation time know which topic/era the messages came from.

EMBEDDING + STORE:
  sentence-transformers (all-MiniLM-L6-v2, 384-d, normalized) -> Chroma
  PersistentClient (cosine). We compute embeddings ourselves so the model is
  explicit and reused identically at query time.

Usage:
    python scripts/build_index.py                      # build from documents/telegram
    python scripts/build_index.py --rebuild            # wipe + rebuild the collection
    python scripts/build_index.py --dry-run            # chunk + report, no embedding
    python scripts/build_index.py --query "is Prof McAlister an easy grader?"
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

# --- Tunables -----------------------------------------------------------------
TARGET_CHARS = 1000   # soft size we pack messages up to (~250 tokens for MiniLM)
MAX_CHARS = 1400      # hard cap; a block over this is split on message boundaries
MIN_CHARS = 80        # blocks shorter than this are merged forward (anti-fragment)
OVERLAP_MSGS = 1      # messages carried over between sub-chunks of a split block

MODEL_NAME = "all-MiniLM-L6-v2"
COLLECTION = "minerva_guide"
DEFAULT_DOCS = "documents/telegram"
DEFAULT_DB = "chroma_db"

CONV_RE = re.compile(r"^--- Conversation (\d+) \((\d{4}-\d{2}-\d{2})\) ---\s*$")
TOPIC_RE = re.compile(r"^# Topic: (.+?)\s*$")
MSG_RE = re.compile(r"^(User_[0-9a-f]{6}): ")


@dataclass
class Block:
    """One conversation thread parsed out of a topic .txt file."""
    topic: str
    file: str
    conv: int
    date: str
    messages: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.messages)


@dataclass
class Chunk:
    cid: str
    text: str
    topic: str
    file: str
    date: str
    conv: int
    sub: int
    n_messages: int


# --- Parsing ------------------------------------------------------------------
def parse_blocks(path: Path) -> list[Block]:
    """Split a topic .txt back into conversation blocks.

    Message bodies can span multiple lines (a single Telegram message with
    newlines), so a line that doesn't start a new "User_xxxxxx:" is appended to
    the current message.
    """
    topic = path.stem
    blocks: list[Block] = []
    cur: Block | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        mt = TOPIC_RE.match(raw)
        if mt:
            topic = mt.group(1)
            continue
        mc = CONV_RE.match(raw)
        if mc:
            cur = Block(topic, str(path), int(mc.group(1)), mc.group(2))
            blocks.append(cur)
            continue
        if cur is None:
            continue
        if MSG_RE.match(raw):
            cur.messages.append(raw)
        elif cur.messages:           # continuation line of the previous message
            cur.messages[-1] += "\n" + raw
        elif raw.strip():            # stray text before any author line
            cur.messages.append(raw)
    return [b for b in blocks if b.messages]


# --- Chunking -----------------------------------------------------------------
def merge_tiny(blocks: list[Block]) -> list[Block]:
    """Merge blocks shorter than MIN_CHARS forward into the next same-topic block."""
    out: list[Block] = []
    carry: Block | None = None
    for b in blocks:
        if carry is not None:
            b = Block(b.topic, b.file, carry.conv, carry.date,
                      carry.messages + b.messages)
            carry = None
        if len(b.text) < MIN_CHARS:
            carry = b                # hold it, fold into the next block
            continue
        out.append(b)
    if carry is not None:            # trailing tiny block: keep rather than drop
        out.append(carry)
    return out


def split_block(b: Block) -> list[list[str]]:
    """Pack a block's messages into groups, each kept under MAX_CHARS.

    Long single messages are first hard-split into TARGET_CHARS windows. We then
    greedily pack to TARGET_CHARS; the carried overlap is capped so a group can
    never exceed roughly MAX_CHARS even after re-seeding from the previous group.
    """
    if len(b.text) <= MAX_CHARS:
        return [b.messages]
    # No single message may exceed TARGET_CHARS, so a group can't blow past MAX.
    msgs: list[str] = []
    for m in b.messages:
        if len(m) <= TARGET_CHARS:
            msgs.append(m)
        else:
            msgs += [m[j:j + TARGET_CHARS] for j in range(0, len(m), TARGET_CHARS)]

    overlap_cap = MAX_CHARS - TARGET_CHARS   # keep group <= ~MAX after overlap
    groups: list[list[str]] = []
    cur: list[str] = []
    size = 0
    for msg in msgs:
        if cur and size + len(msg) + 1 > TARGET_CHARS:
            groups.append(cur)
            ov = cur[-OVERLAP_MSGS:] if OVERLAP_MSGS else []
            if sum(len(m) + 1 for m in ov) > overlap_cap:
                ov = []                       # overlap too big — drop it this time
            cur = list(ov)
            size = sum(len(m) + 1 for m in cur)
        cur.append(msg)
        size += len(msg) + 1
    if cur:
        groups.append(cur)
    return groups


def chunk_blocks(blocks: list[Block]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for b in merge_tiny(blocks):
        groups = split_block(b)
        for sub, msgs in enumerate(groups):
            header = f"Topic: {b.topic} | {b.date}"
            body = "\n".join(msgs)
            stem = Path(b.file).stem
            chunks.append(Chunk(
                cid=f"{stem}::{b.conv}::{sub}",
                text=f"{header}\n{body}",
                topic=b.topic, file=b.file, date=b.date,
                conv=b.conv, sub=sub, n_messages=len(msgs),
            ))
    return chunks


def build_chunks(docs_dir: Path) -> list[Chunk]:
    files = sorted(p for p in docs_dir.glob("*.txt"))
    all_chunks: list[Chunk] = []
    for path in files:
        all_chunks.extend(chunk_blocks(parse_blocks(path)))
    return all_chunks


# --- Reporting ----------------------------------------------------------------
def report(chunks: list[Chunk]) -> None:
    import statistics as s
    lens = sorted(len(c.text) for c in chunks)
    by_topic: dict[str, int] = {}
    for c in chunks:
        by_topic[c.topic] = by_topic.get(c.topic, 0) + 1
    print(f"Chunks: {len(chunks)}")
    print(f"Chunk chars: min={lens[0]} median={int(s.median(lens))} "
          f"mean={int(s.mean(lens))} p95={lens[int(len(lens)*.95)]} max={lens[-1]}")
    print(f"Over MAX_CHARS ({MAX_CHARS}): {sum(1 for x in lens if x > MAX_CHARS)}")
    print("\nChunks per topic (top 12):")
    for t, n in sorted(by_topic.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {t[:45]:45} {n}")


# --- Embedding + Chroma -------------------------------------------------------
def get_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


def get_collection(db_path: str, rebuild: bool):
    import chromadb
    client = chromadb.PersistentClient(path=db_path)
    if rebuild:
        try:
            client.delete_collection(COLLECTION)
        except Exception:
            pass
    return client.get_or_create_collection(
        name=COLLECTION, metadata={"hnsw:space": "cosine"})


def embed_and_store(chunks: list[Chunk], db_path: str, rebuild: bool) -> None:
    model = get_model()
    col = get_collection(db_path, rebuild)
    batch = 512
    for i in range(0, len(chunks), batch):
        part = chunks[i:i + batch]
        embs = model.encode([c.text for c in part], normalize_embeddings=True,
                             show_progress_bar=False)
        col.add(
            ids=[c.cid for c in part],
            documents=[c.text for c in part],
            embeddings=[e.tolist() for e in embs],
            metadatas=[{"topic": c.topic, "file": c.file, "date": c.date,
                        "conv": c.conv, "n_messages": c.n_messages} for c in part],
        )
        print(f"  embedded {min(i + batch, len(chunks))}/{len(chunks)}")
    print(f"Collection '{COLLECTION}' now holds {col.count()} chunks at {db_path}/")


def query(db_path: str, text: str, k: int = 5) -> None:
    model = get_model()
    col = get_collection(db_path, rebuild=False)
    q = model.encode([text], normalize_embeddings=True)[0].tolist()
    res = col.query(query_embeddings=[q], n_results=k)
    print(f"\nQuery: {text!r}\n")
    for rank, (doc, meta, dist) in enumerate(zip(
            res["documents"][0], res["metadatas"][0], res["distances"][0]), 1):
        snippet = doc if len(doc) < 600 else doc[:600] + " …"
        print(f"[{rank}] topic={meta['topic']}  date={meta['date']}  "
              f"cosine_sim={1 - dist:.3f}")
        print(snippet)
        print("-" * 70)


# --- CLI ----------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Chunk + embed Telegram docs into Chroma.")
    ap.add_argument("--docs", default=DEFAULT_DOCS, help="folder of per-topic .txt files")
    ap.add_argument("--db", default=DEFAULT_DB, help="Chroma persist path")
    ap.add_argument("--rebuild", action="store_true", help="wipe the collection first")
    ap.add_argument("--dry-run", action="store_true", help="chunk + report only, no embedding")
    ap.add_argument("--query", help="run a retrieval test against an existing index")
    ap.add_argument("-k", type=int, default=5, help="results to show for --query")
    args = ap.parse_args()

    if args.query:
        query(args.db, args.query, args.k)
        return

    chunks = build_chunks(Path(args.docs))
    report(chunks)
    if args.dry_run:
        print("\n(dry run — nothing embedded)")
        return
    print()
    embed_and_store(chunks, args.db, args.rebuild)


if __name__ == "__main__":
    main()
