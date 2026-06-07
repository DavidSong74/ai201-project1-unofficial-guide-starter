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
`minerva_guide`, with `source`/`chunk_index`/`topic`/`date` metadata for attribution and
optional filtering.

**Two-stage retrieval (added after evaluation):** (1) dense ANN pulls a wide candidate
pool of **40** chunks; (2) a **cross-encoder reranker** (`cross-encoder/ms-marco-MiniLM-L-6-v2`,
same library, no new dependency) rescores each (query, chunk) pair *jointly* and we keep
the top **k=6**. The cross-encoder reads question and answer together, so it fixes the
question↔answer asymmetry a bi-encoder alone has (see Challenge 1). Measured effect: the
Prof McAllister review went from dense rank **#9 → #1** and the "best healthcare city"
answer from **#3 → #1**, with no regression on queries that were already rank-1.

**Top-k:** **6** chunks to the LLM (tunable via `-k`), drawn from the 40-candidate pool by
the reranker — enough corroborating replies without flooding the model. `--no-rerank`
toggles back to dense-only for comparison.

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

<!-- Questions chosen to span the domain's subtopics (academics, immigration, housing,
     health, careers) and to have a checkable answer grounded in a specific chat thread. -->

| # | Question | Expected answer |
|---|----------|-----------------|
| 1 | Is Prof Odera a strict grader or an easy grader? | Strict with grades; explicitly *not* the easy-grader a student was hoping for, though more lenient on class participation. (Prof reviews, 2023-01-04) |
| 2 | How have students gotten an O-1 visa after Minerva, and what resources are mentioned? | The chat has **no step-by-step process** — a correct answer surfaces resources and says so. Resources present: a Dyer Harris law-firm O-1B webinar tied to the OPT period (Visas, 2026) and Global Student Services peer-advising OHs, Mondays 6pm PST, for visa/work-authorization questions (Visas, 2023). NOTE (verified): retrieval is **phrasing-sensitive** here — which resource surfaces depends on wording — and answers can leak an advisor's first name from message bodies (known PII limitation). |
| 3 | Which neighborhoods are best to live in during the Buenos Aires rotation? | Palermo, Recoleta, and Puerto Madero are named as best; the residence hall is in Recoleta (one of the safest); avoid La Boca/San Telmo at night and passing through Retiro at night. (Misc, 2020-04-08) |
| 4 | Which rotation city did students rate as the best healthcare experience? | Korea is rated the best medical experience on rotation (hospital handled everything, no upfront payment/reimbursement), with Taiwan a close second; insurance covered everything except a COVID test. (Healthcare, 2023-05-10) |
| 5 | Can you do an internship part-time during a semester, and how? | Constrained: F1 students can't work in year 1, and US internships are capped at ~20 hrs/week during a semester (Interns corner / Opportunities, 2024). Startups are the most viable for part-time since full-time mid-semester approval (PRPC) is hard, and requesting a mid/late-August start for a summer role can work (Software/Engineering, 2024-05-01). |

---

## Anticipated Challenges

1. **Question↔answer embedding asymmetry.** With a symmetric bi-encoder (all-MiniLM-L6-v2),
   a query phrased as a question ("how is Prof X?") embeds nearest to *other questions*
   rather than to the declaratively-phrased *answer* ("I had her, she's great"). Verified:
   a real positive Prof McAllister review was indexed but ranked #9, below the cutoff, so
   the system wrongly refused. **RESOLVED** by the two-stage cross-encoder reranker (see
   Retrieval Approach): it reads query+chunk jointly and lifted that review #9→#1. I first
   tested BM25 as a fix and *rejected it on evidence* — BM25 ranked the review #11 (worse),
   because "McAllister" recurs in many *question* chunks; the reranker, not keywords, was
   the right tool. (BM25/hybrid still helps a different class — exact-token queries like the
   "best healthcare city" answer, which BM25 ranked #1 — so it's a documented future add.)

2. **A dominant noisy bucket.** "Misc / Untagged" is 25,072 messages → 5,806 chunks (~47%
   of the index). Off-topic or low-signal chunks from it can crowd out the right thread,
   and it mixes many subtopics under one label. Mitigation: the `topic` metadata supports
   filtering, and a relevance floor drops weak matches.

3. **Contradictory / outdated peer info.** This is years of opinions: professors leave,
   policies and visa rules change, a "best" city in 2020 may differ now. The model can
   merge a 2021 claim with a 2026 one. Mitigation: every chunk carries a date, surfaced in
   citations, and the system prompt tells the model to flag disagreement and one-off
   experiences.

4. **Residual PII (ethics).** Author handles, phones, emails and @mentions are scrubbed,
   but personal *names written in message bodies* (e.g. "ask Marianna") are not — NER would
   risk false positives on common first names. Documented limitation; this corpus is real
   classmates' private messages, which is also why embedding/generation stay local + a
   private Groq key rather than logging data to a third party.

5. **Topic membership is only partially recoverable from the export.** The Telegram
   Desktop JSON has *no per-message topic field* — only `reply_to_message_id` (present on
   29,224 / 45,179 messages). Topic files are therefore reconstructed by walking reply
   chains up to each `topic_created` root, which captures only *explicitly-threaded*
   messages. Verified failure: `general.txt` stops in 2022 (887 msgs chain to the General
   root, all in 2022; ~0 after) because **"General" is Telegram's default topic and its
   messages are not reply-linked to the topic root** — so post-2022 general chat is
   indistinguishable from untagged chatter and falls into `misc-untagged.txt`. This is also
   why that bucket is so large (~55% of messages). Net effect: per-topic retrieval
   under-covers any topic where users posted without explicitly replying in-thread.
   Mitigation: keep the Misc bucket indexed (so the content is still retrievable, just
   without a clean topic label) and rely on dense similarity rather than topic filtering
   for recall.

---

## Architecture

```
[1] DOCUMENT INGESTION            scripts/telegram_export.py
    Telegram JSON export (result.json, 45,179 msgs)
      → resolve forum topics / reply anchors
      → scrub PII (handles→User_xxxxxx, phone/email/@mention→placeholder)
      → time-gap segment into conversation threads
      → 29 per-topic .txt + manifest.json
                     │
                     ▼
[2] CHUNKING                      scripts/build_index.py
    1 conversation thread = 1 chunk (median ~315 chars)
      → split oversized threads on message boundaries (target 1,000 chars, 1-msg overlap)
      → merge <80-char threads forward
      → prefix "Topic: <name> | <date>"      ⇒ 12,337 chunks
                     │
                     ▼
[3] EMBEDDING + VECTOR STORE      sentence-transformers + Chroma
    all-MiniLM-L6-v2 (384-d, normalized, cosine)
      → Chroma PersistentClient @ chroma_db/, collection "minerva_guide"
                     │
                     ▼
[4] RETRIEVAL (two-stage)         scripts/ask.py → build_index.search()
    embed question → dense ANN top-40 candidates (cosine)
      → cross-encoder rerank (ms-marco-MiniLM-L-6-v2) → keep top-6
      → drop chunks below MIN_SIM=0.25  (refuse if none clear it)
                     │
                     ▼
[5] GENERATION                    Groq  llama-3.3-70b-versatile
    grounded system prompt (answer ONLY from numbered context, cite [n], else "I don't know")
      → answer with inline [n] citations + Sources list (topic | date | sim)
```

---

## AI Tool Plan

Tool used: **Claude (Claude Code)**, driven section-by-section from this planning.md.

**Milestone 3 — Ingestion and chunking:** Give Claude a sample of the raw Telegram JSON
plus the Domain/Documents spec and ask it to write `telegram_export.py` (topic detection,
PII scrub, time-gap segmentation). Verify by running `--inspect` on the real export and
spot-reading output files to confirm handles/phones/emails are redacted and topics are
sensible — *done; caught and corrected an early wrong assumption that the chat had no
native forum topics.*

**Milestone 4 — Embedding and retrieval:** Give Claude the Chunking Strategy + Retrieval
Approach sections and ask it to implement `build_index.py` with thread-aware chunking,
the stated 1,000-char target / 1-msg overlap, MiniLM embeddings, and Chroma persistence.
Verify with a `--dry-run` chunk-size histogram (must fit the 256-token window) and
sample `--query` retrievals — *done; caught an overlap bug producing 2,847-char chunks and
fixed the splitter.*

**Milestone 5 — Generation and interface:** Give Claude the Grounded Generation spec and
ask it to implement `ask.py` (retrieve → relevance floor → Groq with the grounding system
prompt → cited answer). Verify with the 5 evaluation questions above plus an
out-of-corpus question to confirm the refusal path — *done; surfaced the McAllister
retrieval failure.* Next: optional gradio/streamlit UI over the same `retrieve`/`generate`
functions.
