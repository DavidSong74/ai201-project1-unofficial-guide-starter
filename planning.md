# Project 1 Planning: The Unofficial Guide

> Write this document before you write any pipeline code.
> Your spec and architecture diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Update the Retrieval Approach and Chunking Strategy sections if you change your approach during implementation.
> Update this file before starting any stretch features.

---

## Domain

**Insider survival knowledge for Minerva University students** — the practical,
lived-experience side of being a student who rotates through seven global cities:
which professors grade how and which courses are worth taking, immigration paths
(F-1/OPT, O-1/O-1B visas), international travel and relocation logistics, healthcare
abroad, jobs/internships/scholarships, and university bureaucracy. This knowledge is
valuable because none of it appears in official course catalogs or the registrar's
pages — it is tacit, peer-to-peer, and constantly updated by students who just went
through it. It is hard to find because it lives buried in **~45,000 messages** across
years of a private cross-cohort Telegram chat, where the answer to "has anyone actually
gotten an O-1 visa?" is a single 2025 reply you would never surface by scrolling.

---

## Documents

<!-- "Sources" here are the topical reply-threads inside one Telegram export
     (Minerva Cross-Class Chat, JSON, 45,179 messages). The export's 28 native forum
     topics each act as a distinct source document covering a different subtopic. -->

Source corpus: **Minerva Cross-Class Chat**, Telegram Desktop JSON export
(`result.json`, 45,179 messages, 2021–2026), split by `scripts/telegram_export.py`
into one document per forum topic. The topics below cover distinct, non-overlapping
subtopics (academics, immigration, logistics, careers, health, admin) — not ten
threads that all say the same thing.

| # | Source (topic thread) | Description | Location |
|---|--------|-------------|-----------------|
| 1 | CS | CS course/section advice, tooling, workload (2,621 msgs) | documents/telegram/cs.txt |
| 2 | Opportunities | Jobs, internships, scholarships, grants (1,774 msgs) | documents/telegram/opportunities-jobs-intern-scholarships-etc.txt |
| 3 | Minerva Bureaucracy | Registrar, deadlines, policy, admin workarounds (1,480 msgs) | documents/telegram/minerva-bureaucracy.txt |
| 4 | Visas | F-1/OPT, O-1/O-1B immigration experiences (1,361 msgs) | documents/telegram/visas.txt |
| 5 | Travel | Cross-city relocation, flights, housing logistics (1,336 msgs) | documents/telegram/travel.txt |
| 6 | SS | Social Sciences course/professor reviews (1,075 msgs) | documents/telegram/ss.txt |
| 7 | Classes exchange | Add/drop swaps and section-selection advice (1,007 msgs) | documents/telegram/classes-exchange.txt |
| 8 | AH | Arts & Humanities course/professor reviews (1,001 msgs) | documents/telegram/ah.txt |
| 9 | NS | Natural Sciences course/professor reviews (914 msgs) | documents/telegram/ns.txt |
| 10 | Prof reviews | Cross-college professor grading/teaching reviews (594 msgs) | documents/telegram/prof-reviews.txt |
| 11 | Interns corner | Internship hunt + workplace experiences (401 msgs) | documents/telegram/interns-corner.txt |
| 12 | Healthcare | Seeing doctors / insurance across rotation cities (319 msgs) | documents/telegram/healthcare.txt |

(16 further topics — Business, ASM, After Minerva, Tutorials, etc. — are also indexed;
full list with counts in `documents/telegram/manifest.json`.)

---

## Chunking Strategy

**Chunk unit: one conversation thread** (not a fixed-size window). `telegram_export.py`
already segments each topic into reply-threads cut on 180-minute time gaps, so a thread
is a self-contained Q&A (a question + the replies that answer it). Implemented in
`scripts/build_index.py`.

**Chunk size:** target **1,000 chars (~250 tokens)**, hard cap ~1,400. I measured the
real data first: across 10,192 threads the median is **315 chars**, p90 1,394, p95 2,145.
So ~90% of threads fit in one chunk untouched. The few long threads are split **on
message boundaries** (never mid-message) up to the target size.

**Overlap:** **1 message** carried between sub-chunks of a split thread (capped so a
sub-chunk can't exceed the size limit). Overlap matters only for the ~5% of threads long
enough to split — it keeps the question attached to the reply when a thread is divided.
Threads under **80 chars** (e.g. "thanks!!") are merged forward into the next thread so
we never embed a lone fragment.

**Reasoning:** A chat corpus is question/answer threads, not prose, so the semantic unit
is the thread, not an arbitrary 500-char slice — splitting mid-thread would separate
"is Prof X an easy grader?" from "yes, very." Target size is set to ~250 tokens to fit
the embedding model's 256-token window (see below) so chunks aren't silently truncated.
Each chunk is prefixed with a `Topic: <name> | <date>` header so both the embedding and
the LLM know the topic and era. **Final chunk count: 12,337.**

---

## Retrieval Approach

**Embedding model:** `all-MiniLM-L6-v2` via sentence-transformers (384-dim, normalized,
cosine). Fast and free on CPU (full corpus embeds in ~90s), and strong on short
conversational English. Its 256-token window is the constraint that set my 1,000-char
chunk target. Vector store: **Chroma** `PersistentClient` (cosine space), collection
`minerva_guide`, with `topic`/`date`/`file` metadata for optional filtering.

**Top-k:** **5** (tunable via `-k`). Smoke tests show the relevant thread lands at rank 1
with cosine_sim ≈ 0.60–0.64; k=5 gives the LLM corroborating replies without flooding it
with low-relevance chunks.

**Production tradeoff reflection:** If cost weren't a constraint I'd weigh (1) **context
length** — MiniLM's 256-token cap truncates long threads; a 512–8k-token model
(`bge-base`, OpenAI `text-embedding-3-large`) would let me embed whole threads without
splitting; (2) **multilingual** — this chat mixes languages, and MiniLM is English-centric,
so a multilingual model (`paraphrase-multilingual-mpnet`, Cohere multilingual) would
retrieve non-English messages better; (3) **domain accuracy** — Minerva jargon
("cornerstone", "EA", section codes like SS51) is out-of-distribution; a larger or
fine-tuned model would embed those more faithfully; (4) **latency/hosting** — an API
model adds per-query latency and sends private student data off-device, which for *this*
corpus is a real privacy cost, so local embedding is actually the right call here even
ignoring money.

---

## Evaluation Plan

<!-- List your 5 test questions with their expected correct answers.
     Questions should be specific enough that you can judge whether the system's response
     is right or wrong. "What are good dining halls?" is too vague.
     "What do students say about wait times at [dining hall name] during lunch?" is testable. -->

| # | Question | Expected answer |
|---|----------|-----------------|
| 1 | | |
| 2 | | |
| 3 | | |
| 4 | | |
| 5 | | |

---

## Anticipated Challenges

<!-- What could go wrong? Name at least two specific risks with reasoning.
     Consider: noisy or inconsistent documents, missing source attribution, off-topic
     retrieval, chunks that split key information across boundaries. -->

1.

2.

---

## Architecture

<!-- Draw a diagram of your pipeline showing the five stages:
     Document Ingestion → Chunking → Embedding + Vector Store → Retrieval → Generation
     Label each stage with the tool or library you're using.
     You can use ASCII art, a Mermaid diagram, or embed a sketch as an image.
     You'll use this diagram as context when prompting AI tools to implement each stage. -->

---

## AI Tool Plan

<!-- For each part of the pipeline below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, which requirements)
     - What you expect it to produce
     - How you'll verify the output matches your spec

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Chunking Strategy section and ask it to implement chunk_text()
     with my specified chunk size and overlap" is a plan. -->

**Milestone 3 — Ingestion and chunking:**

**Milestone 4 — Embedding and retrieval:**

**Milestone 5 — Generation and interface:**
