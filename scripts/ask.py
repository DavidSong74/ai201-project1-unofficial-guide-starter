#!/usr/bin/env python3
"""Grounded question answering over the Telegram chat index (Milestone 5).

Pipeline: embed the question -> dense ANN over a wide candidate pool -> cross-encoder
rerank to top-k (build_index.search) -> drop chunks below a relevance floor -> feed
ONLY those chunks to a Groq LLM under a strict "answer only from the context" system
prompt -> print the answer with inline [n] citations and a Sources list so every claim
is traceable.

GROUNDING MECHANISM (two layers):
  1. Structural — the model never sees the raw corpus, only the reranked chunks,
     each numbered and labelled "[n] Topic | date". If the best reranker score is
     below CE_REFUSE we refuse outright (the LLM is never called), so it cannot
     fall back on its own knowledge.
  2. Prompted — the system prompt forbids outside knowledge, asks for hedged
     POINTERS with [n] citations, and requires "I don't know" when context is thin.

OUTPUT: the LLM writes paraphrased pointers (it must NOT quote verbatim); the code
attaches the real, lightly PII-scrubbed excerpt under each source — so quotes are
guaranteed faithful (the model can't fabricate one) — plus a confidence banner driven
by the cross-encoder score.

Usage:
    python scripts/ask.py "Is Prof McAlister an easy grader?"
    python scripts/ask.py "How do people get an O-1 visa after Minerva?" -k 6
    python scripts/ask.py "What's the best city for an internship?" --show-context
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import textwrap

import dotenv
import groq

from build_index import DEFAULT_DB, search

MODEL = "llama-3.3-70b-versatile"
TOP_K = 6             # chunks fed to the LLM after reranking (widened from 5)
TEMPERATURE = 0.2

# Confidence/refusal thresholds on the cross-encoder score of the BEST hit.
# Calibrated on real queries: strong answers score > 2 (Odera 8.7, McAllister 2.5,
# healthcare 2.9); off-corpus goes negative (pasta -9.9, wifi -1.4).
CE_STRONG = 2.0       # >= this -> confident, no banner
CE_MODERATE = 0.0     # >= this -> "moderate"; below -> "low-confidence"
CE_REFUSE = -4.0      # best hit below this -> refuse (don't call the LLM)

SYSTEM_PROMPT = """\
You are the "Unofficial Guide" to Minerva University — a peer knowledge base built from \
a private student group chat (lived experience and opinions, NOT official policy).

Answer the question as a short set of practical POINTERS grounded ONLY in the numbered \
context.

Rules:
- Use ONLY the numbered context. Never use outside knowledge.
- Write 1-4 concise bullet pointers. End each pointer with its source number(s), e.g. [2][4].
- Do NOT quote the messages verbatim — paraphrase into a pointer. (Exact excerpts are \
shown separately to the user under Sources.)
- These are individual, sometimes outdated or conflicting opinions. Hedge honestly: \
attribute one-off claims ("one student said..."), flag disagreement, and note the year \
when it matters.
- If the context does not answer the question, say exactly: "The chat doesn't have a \
clear answer on that." Do not guess or invent.
- Be concrete: name professors, cities, dollar amounts, and steps when the context does."""


# Light, heuristic display-time PII scrub for the verbatim excerpts (NOT a substitute
# for NER — see planning.md Challenge 4). Masks first names in three contexts: contact
# directives ("ask Sarah"), contact-info possessives ("Marianna's number"), and
# attributions ("according to Marianna"). A stoplist guards against masking orgs/places.
_CONTACT_VERB = re.compile(
    r"\b(ask(?:ing)?|contact|dm|message|msg|text|email(?:ing)?|ping|reach(?:\s+out)?(?:\s+to)?)"
    r"\s+([A-Z][a-z]+)\b")
_CONTACT_NOUN = re.compile(
    r"\b([A-Z][a-z]+)('s)?\s+(whatsapp|telegram|instagram|insta|number|phone)\b")
_ATTRIB = re.compile(r"\b(according to|per|asked)\s+([A-Z][a-z]+)\b")

# Capitalized tokens that are NOT personal names (orgs, places, time, schools, etc.).
_NON_PERSON = {
    "Minerva", "Google", "Manifest", "Slack", "Zoom", "Cigna", "Forum", "Telegram",
    "Whatsapp", "Instagram", "Korea", "Taiwan", "Argentina", "Berlin", "Seoul", "London",
    "Hyderabad", "Taipei", "San", "Buenos", "America", "Europe", "China", "India",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December", "The", "This", "That", "It", "OPT",
}


def scrub(text: str) -> str:
    text = _CONTACT_VERB.sub(
        lambda m: m.group(0) if m.group(2) in _NON_PERSON else f"{m.group(1)} [name]", text)
    text = _CONTACT_NOUN.sub(lambda m: f"[name]{m.group(2) or ''} {m.group(3)}", text)
    text = _ATTRIB.sub(
        lambda m: m.group(0) if m.group(2) in _NON_PERSON else f"{m.group(1)} [name]", text)
    return text


def excerpt(text: str, width: int = 260) -> str:
    """One-line, scrubbed, shortened version of a chunk for display under Sources."""
    body = text.split("\n", 1)[1] if text.startswith("Topic:") and "\n" in text else text
    body = " ".join(body.split())
    return textwrap.shorten(scrub(body), width=width, placeholder=" …")


def retrieve(db_path: str, question: str, k: int) -> list[dict]:
    # dense recall over a wide candidate pool, then cross-encoder rerank to top-k
    return search(db_path, question, k)


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
    kept = [h for h in hits if h["ce"] >= CE_REFUSE]   # drop clearly-irrelevant chunks

    print(f"\nQ: {question}\n")
    if not kept:
        print("The chat doesn't have a clear answer on that "
              f"(no chunk cleared the reranker floor, ce ≥ {CE_REFUSE}).")
        return

    context = build_context(kept)
    if show_context:
        print("=== Retrieved context ===")
        print(context)
        print("=========================\n")

    client = groq.Groq(api_key=api_key)
    answer = generate(client, question, context)

    top_ce = kept[0]["ce"]
    if top_ce < CE_MODERATE:
        print("⚠️  Low-confidence: the closest sources are only weakly related — "
              "treat this as a weak signal.\n")
    elif top_ce < CE_STRONG:
        print("⚠️  Moderate-confidence: sources are loosely on-topic — "
              "double-check specifics.\n")

    print(answer)
    print("\nSources (verbatim excerpts, lightly PII-scrubbed):")
    for i, h in enumerate(kept, 1):
        m = h["meta"]
        print(f"  [{i}] {m['source']} (chunk #{m['chunk_index']}) · "
              f"{m['topic']} · {m['date']} · relevance {h['ce']:.1f}")
        print(f'      "{excerpt(h["text"])}"')


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
