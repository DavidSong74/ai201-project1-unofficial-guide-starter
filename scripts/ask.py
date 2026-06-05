#!/usr/bin/env python3
"""Grounded question answering over the Telegram chat index (Milestone 5).

Pipeline: embed the question -> retrieve top-k chunks from Chroma -> drop chunks
below a relevance floor -> feed ONLY those chunks to a Groq LLM under a strict
"answer only from the context" system prompt -> print the answer with inline [n]
citations and a Sources list (topic + date) so every claim is traceable.

GROUNDING MECHANISM (two layers):
  1. Structural — the model never sees the raw corpus, only the retrieved chunks,
     each numbered and labelled "[n] Topic | date". Chunks under MIN_SIM cosine
     similarity are filtered out; if nothing clears the floor we refuse to answer
     rather than let the model fall back on its own knowledge.
  2. Prompted — the system prompt forbids outside knowledge, requires [n] citations,
     and requires "I don't know" when the context is insufficient.

Usage:
    python scripts/ask.py "Is Prof McAlister an easy grader?"
    python scripts/ask.py "How do people get an O-1 visa after Minerva?" -k 6
    python scripts/ask.py "What's the best city for an internship?" --show-context
"""

from __future__ import annotations

import argparse
import os
import sys

import dotenv
import groq

from build_index import DEFAULT_DB, get_collection, get_model

MODEL = "llama-3.3-70b-versatile"
TOP_K = 5
MIN_SIM = 0.25        # cosine-similarity floor; below this a chunk is treated as noise
TEMPERATURE = 0.2

SYSTEM_PROMPT = """\
You are the "Unofficial Guide" to Minerva University. You answer using ONLY the \
numbered context below, which are excerpts from a private student group chat \
(peer opinions and lived experience, not official university policy).

Rules:
- Use ONLY information in the numbered context. Do not use outside knowledge.
- Cite every claim with the source number(s) in square brackets, e.g. [2].
- If the context does not contain the answer, say so plainly: "The chat doesn't \
have a clear answer on that." Do not guess or invent details.
- These are individual student opinions and may be outdated or contradictory. \
When sources disagree or a claim is one person's experience, say so.
- Be concise and concrete. Quote specifics (professor names, cities, steps) when present."""


def retrieve(db_path: str, question: str, k: int) -> list[dict]:
    model = get_model()
    col = get_collection(db_path, rebuild=False)
    q = model.encode([question], normalize_embeddings=True)[0].tolist()
    res = col.query(query_embeddings=[q], n_results=k)
    hits = []
    for doc, meta, dist in zip(
            res["documents"][0], res["metadatas"][0], res["distances"][0]):
        hits.append({"text": doc, "meta": meta, "sim": 1 - dist})
    return hits


def build_context(hits: list[dict]) -> str:
    parts = []
    for i, h in enumerate(hits, 1):
        m = h["meta"]
        parts.append(f"[{i}] Topic: {m['topic']} | {m['date']}\n{h['text']}")
    return "\n\n".join(parts)


def generate(client: groq.Groq, question: str, context: str) -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=TEMPERATURE,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",
             "content": f"Context:\n\n{context}\n\nQuestion: {question}"},
        ],
    )
    return resp.choices[0].message.content.strip()


def ask(db_path: str, question: str, k: int, show_context: bool) -> None:
    dotenv.load_dotenv(dotenv_path=".env")
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key == "your_key_here":
        sys.exit("GROQ_API_KEY is not set. Copy .env.example to .env and add your key.")

    hits = retrieve(db_path, question, k)
    kept = [h for h in hits if h["sim"] >= MIN_SIM]

    if not kept:
        print(f"\nQ: {question}\n")
        print("The chat doesn't have a clear answer on that "
              f"(no chunk cleared the {MIN_SIM} relevance floor).")
        return

    context = build_context(kept)
    if show_context:
        print("=== Retrieved context ===")
        print(context)
        print("=========================\n")

    client = groq.Groq(api_key=api_key)
    answer = generate(client, question, context)

    print(f"\nQ: {question}\n")
    print(answer)
    print("\nSources:")
    for i, h in enumerate(kept, 1):
        m = h["meta"]
        print(f"  [{i}] {m['source']} (chunk #{m['chunk_index']}) | "
              f"{m['topic']} | {m['date']} (sim {h['sim']:.2f})")


def main() -> None:
    ap = argparse.ArgumentParser(description="Grounded Q&A over the Telegram index.")
    ap.add_argument("question", help="the question to answer")
    ap.add_argument("--db", default=DEFAULT_DB, help="Chroma persist path")
    ap.add_argument("-k", type=int, default=TOP_K, help="chunks to retrieve")
    ap.add_argument("--show-context", action="store_true",
                    help="print the retrieved chunks before the answer")
    args = ap.parse_args()
    ask(args.db, args.question, args.k, args.show_context)


if __name__ == "__main__":
    main()
