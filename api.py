#!/usr/bin/env python3
"""FastAPI backend for the web/ interface — wraps the existing RAG pipeline.

It reuses build_index.search() (dense + cross-encoder rerank) and ask.py's grounded
generation, and returns exactly the JSON shape the frontend's askQuestion() expects:

    POST /ask  { "question": str, "k": int }
    -> { answer, refused, confidence: "high"|"moderate"|"low",
         sources: [{ n, source_file, topic, date, relevance, excerpt }] }

Run:
    uvicorn api:app --port 8000 --reload      # then `npm run dev` in web/ (proxies /ask)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import dotenv
import groq
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Reuse the pipeline that lives in scripts/.
sys.path.insert(0, str(Path(__file__).parent / "scripts"))
import build_index  # noqa: E402
import ask as askmod  # noqa: E402

DB_PATH = build_index.DEFAULT_DB

dotenv.load_dotenv(dotenv_path=str(Path(__file__).parent / ".env"))
_api_key = os.getenv("GROQ_API_KEY")
if not _api_key or _api_key == "your_key_here":
    raise SystemExit("GROQ_API_KEY is not set. Add it to .env before starting the API.")
_client = groq.Groq(api_key=_api_key)

app = FastAPI(title="Unofficial Guide to Minerva — API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["POST"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str
    k: int = askmod.TOP_K


def _confidence(top_ce: float) -> str:
    if top_ce >= askmod.CE_STRONG:
        return "high"
    if top_ce >= askmod.CE_MODERATE:
        return "moderate"
    return "low"


@app.on_event("startup")
def _warmup() -> None:
    # Load the embedding + reranker models and open the collection once, up front.
    build_index.search(DB_PATH, "warmup", k=1)


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    hits = build_index.search(DB_PATH, req.question, req.k)
    kept = [h for h in hits if h["ce"] >= askmod.CE_REFUSE]

    if not kept:
        return {"answer": "", "refused": True, "confidence": "low", "sources": []}

    context = askmod.build_context(kept)
    answer = askmod.generate(_client, req.question, context)
    sources = [
        {
            "n": i,
            "source_file": h["meta"]["source"],
            "topic": h["meta"]["topic"],
            "date": h["meta"]["date"],
            "relevance": round(h["ce"], 1),
            "excerpt": askmod.excerpt(h["text"]),
        }
        for i, h in enumerate(kept, 1)
    ]
    return {
        "answer": answer,
        "refused": False,
        "confidence": _confidence(kept[0]["ce"]),
        "sources": sources,
    }
