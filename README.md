# The Unofficial Guide — Project 1

> **How to use this template:**
> Complete each section *after* you've built and tested the corresponding part of your system.
> Do not write placeholder text — if a section isn't done yet, leave it blank and come back.
> Every section below is required for submission. One-liners will not receive full credit.

---

## Domain

<!-- What topic or category of knowledge does your system cover?
     Why is this knowledge valuable, and why is it hard to find through official channels?
     Example: "Student reviews of CS professors at [university] — useful because official
     course descriptions don't reflect teaching style, exam difficulty, or workload." -->

---

## Document Sources

<!-- List every source you collected documents from.
     Be specific: include URLs, subreddit names, forum thread titles, or file names.
     Aim for variety — sources that together cover different subtopics or perspectives. -->

| # | Source | Type | URL or file path |
|---|--------|------|-----------------|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |
| 6 | | | |
| 7 | | | |
| 8 | | | |
| 9 | | | |
| 10 | | | |

---

## Chunking Strategy

<!-- Describe your chunking approach with enough specificity that someone else could reproduce it.
     Include:
     - Chunk size (characters or tokens) and why that size fits your documents
     - Overlap size and why (or why not) you used overlap
     - Any preprocessing you did before chunking (e.g., stripping HTML, removing headers)
     - What your final chunk count was across all documents -->

**Chunk size:** target **1,000 characters (~250 tokens)**, hard cap ~1,400. The chunk
*unit* is one **conversation thread**, not a fixed window — `scripts/telegram_export.py`
segments each topic into reply-threads cut on 180-minute time gaps, and
`scripts/build_index.py` turns each thread into a chunk.

**Overlap:** **1 message** between sub-chunks, and only when a thread is long enough to
be split (~5% of threads). Threads under 80 chars are merged forward into the next thread
instead of being embedded alone.

**Preprocessing:** the JSON export is converted to clean `Author: text` lines with PII
scrubbed (handles → `User_xxxxxx`, phone/email/@mentions → placeholders, URLs preserved),
grouped by topic and time-segmented. Each chunk is prefixed with a `Topic: <name> | <date>`
header for context.

**Why these choices fit your documents:** I measured the corpus before choosing sizes —
across 10,192 threads the median is 315 chars (p90 1,394), so ~90% of threads are already
chunk-sized and splitting on a fixed window would cut "is Prof X easy?" away from its
answer. Splitting only oversized threads, on message boundaries, keeps each Q&A intact.
The 1,000-char target is deliberately set under the embedding model's 256-token window so
chunks aren't silently truncated.

**Final chunk count:** **12,337** chunks across 29 topic files.

---

## Embedding Model

<!-- Name the embedding model you used and explain your choice.
     Then answer: if you were deploying this system for real users and cost wasn't a constraint,
     what tradeoffs would you weigh in choosing a different model?
     Consider: context length limits, multilingual support, accuracy on domain-specific text,
     latency, and local vs. API-hosted. -->

**Model used:** `all-MiniLM-L6-v2` via sentence-transformers (384-dim, normalized
embeddings, cosine similarity), stored in **Chroma** (`PersistentClient`, collection
`minerva_guide`). Chosen because it is fast and free on CPU (the full 12,337-chunk corpus
embeds in ~90s), runs **locally** — which matters here since the data is private student
messages I should not send to a third-party API — and is strong on short conversational
English. Its 256-token window is the constraint that set my ~250-token chunk target.

**Production tradeoff reflection:** If cost weren't a constraint I'd weigh: **(1) context
length** — MiniLM's 256-token cap truncates long threads; a 512–8k-token model
(`bge-base`, OpenAI `text-embedding-3-large`) could embed whole threads without splitting.
**(2) Multilingual** — this chat code-switches between languages and MiniLM is
English-centric, so a multilingual model would retrieve non-English messages better.
**(3) Domain accuracy** — Minerva jargon ("cornerstone", "EA", section codes like SS51)
is out-of-distribution; a larger or fine-tuned embedder would represent it more
faithfully, and an **asymmetric query/passage** model would fix the question↔answer
mismatch documented in the Failure Case. **(4) Latency & privacy** — an API model adds
per-query latency *and* ships private student data off-device, so for this corpus local
embedding is the right call even ignoring money.

---

## Grounded Generation

Implemented in `scripts/ask.py` (Groq `llama-3.3-70b-versatile`, temperature 0.2).
Grounding is enforced at **two layers**, not just by a prompt instruction:

**1. Structural (before the model is called):**
- The model only ever sees the **reranked top-k chunks**, never the raw corpus.
- Each chunk is injected as a numbered, labelled block: `[n] Topic: <name> | <date>`
  followed by the messages — so the model can attribute claims to a specific source.
- A **relevance floor on the cross-encoder score** drops any chunk below `CE_REFUSE = -4`.
  If the best chunk is below it, `ask.py` short-circuits and prints "The chat doesn't have
  a clear answer on that" — the LLM is **never invoked**, so it cannot fall back on its own
  training knowledge. (The reranker score is a better refusal signal than cosine: an
  off-corpus query like "how to cook pasta" scores −9.9 and is refused even though its
  cosine sim, 0.40, would clear a naive cosine floor.)

**2. Output that fits the domain (pointers + faithful quotes):**
- The model is told to answer as **hedged bullet pointers**, each ending in `[n]`
  citations, and **explicitly NOT to quote verbatim**.
- The **verbatim quote is attached by the code**, not the LLM — `ask.py` prints the real
  stored chunk text under each source. This guarantees quotes are faithful (the model
  can't fabricate one) and matches the domain: these are peer anecdotes, so showing the
  raw message lets the reader calibrate trust themselves.
- A **confidence banner** derived from the top reranker score warns on weak retrieval
  (`< 2.0` moderate, `< 0.0` low-confidence), turning silent low-confidence answers into
  visible hedges.
- Displayed excerpts get a **light PII scrub** (masks first names in contact/attribution
  contexts, e.g. "according to Marianna" → "according to [name]", with an org/place
  stoplist) — heuristic, not full NER (see Failure Case / Challenge 4).

**System prompt grounding instruction (verbatim, abridged):**
> You answer using ONLY the numbered context… Never use outside knowledge. Write 1-4
> concise bullet pointers, each ending in its source number(s), e.g. [2][4]. Do NOT quote
> verbatim — paraphrase. These are individual, sometimes outdated or conflicting opinions:
> attribute one-off claims, flag disagreement, note the year. If the context does not
> answer the question, say exactly "The chat doesn't have a clear answer on that."

**How source attribution is surfaced:** the model cites inline `[n]` markers, and `ask.py`
prints a `Sources:` list mapping each `[n]` → `source.txt (chunk #i) · topic · date ·
relevance` followed by the scrubbed verbatim excerpt. Verified across the 5 evaluation
questions (see Evaluation Report) and on the refusal path (off-corpus + diffuse queries
correctly decline instead of fabricating).

---

## Evaluation Report

<!-- Run your 5 test questions from planning.md through your system and record the results.
     Be honest — a partially accurate or inaccurate result that you explain well is more
     valuable than a suspiciously perfect result. -->

Run through the final pipeline (dense → cross-encoder rerank → Groq, with confidence
banner + verbatim scrubbed excerpts). Scores are the reranker relevance of the top source.

| # | Question | Expected answer | System response (summarized) | Retrieval quality | Response accuracy |
|---|----------|-----------------|------------------------------|-------------------|-------------------|
| 1 | Is Prof Odera a strict grader? | Strict, not an easy grader | "Very hard grader / super strict… nice person; one student got good grades with effort." Pointers cite [1][2][3][5]; top source ce 8.7. | Relevant | Accurate |
| 2 | How have students gotten an O-1 visa; what resources? | No how-to exists; surface resources (Dyer Harris O-1B webinar, GSS office hours) | **Refused** — "chat doesn't have a clear answer." Top chunk was an F-1 status update (ce 3.0). | Partially relevant | Partially accurate (honest refusal, but under-delivers the resources that *do* exist) |
| 3 | Best neighborhoods in Buenos Aires? | Palermo/Recoleta/Puerto Madero; avoid Retiro at night | Named all three, flagged Retiro, and *spontaneously* hedged "these opinions are from 2020." [1][2]; ce 4.5. | Relevant | Accurate |
| 4 | Best healthcare city on rotation? | Korea best, Taiwan second | "Korea was the best… Taiwan a close second." [1]; ce 2.9 (reranked from dense #3 → #1). | Relevant | Accurate |
| 5 | Internship part-time during a semester? | F1 limits + startups + Aug start | "Can't work year-1 on F1; startups offer flexibility; ~20 hrs/week cap." [1][2][4][5]; ce 6.0. | Relevant | Accurate |

**Overall: 4/5 accurate, 1 partial.** The reranker fixed Q4 (and the McAllister failure
case) but *regressed Q2*: it optimizes per-chunk answer-relevance, so for a question whose
answer is diffuse (scattered resource pointers rather than one how-to thread) it finds no
strong chunk and refuses. Honest tradeoff — the refusal is safe (no fabrication) but less
useful than the dense-only run, which surfaced the webinar/office-hours pointers. A
rerank+dense fusion (keep a couple of top-cosine chunks alongside the reranked ones) would
recover Q2 without losing the Q4/McAllister gains — documented as a future step.

**Retrieval quality:** Relevant / Partially relevant / Off-target  
**Response accuracy:** Accurate / Partially accurate / Inaccurate

---

## Failure Case Analysis

<!-- Identify at least one question where retrieval or generation did not work as expected.
     Write a specific explanation of *why* it failed, tied to a part of the pipeline.

     "The answer was wrong" is not an explanation.

     "The relevant information was split across a chunk boundary, so retrieval returned
     only half the context — the model didn't have enough to answer correctly" is an explanation.

     "The embedding model treated the professor's nickname as out-of-vocabulary and returned
     results from an unrelated review" is an explanation. -->

**Question that failed:** "What do students say about Prof McAllister as a teacher and
grader?" (k=8)

**What the system returned:** "The chat doesn't have a clear answer on that… there are no
direct comments about her teaching style or grading." This is *wrong* — the chat contains
a clear, positive review: *"I had Prof McAllister in SS152 last semester and I found her
great!… cares about students… gives pretty good grades."*

**Root cause (retrieval stage, not generation):** The generation layer behaved correctly
— it faithfully refused because the answer wasn't in the retrieved context. The failure
is in **retrieval ranking**. I confirmed the review chunk *is* indexed but ranks **#9**
(cosine 0.558), just below the k=8 cutoff. The question is phrased interrogatively ("what
do students say about Prof X?"), and with a symmetric bi-encoder (`all-MiniLM-L6-v2`) it
embeds closest to other **question-shaped** chunks ("how is Prof Y as an instructor?")
rather than the **declaratively-phrased answer** ("I had her, she's great"). Look-alike
*questions* crowd out the actual *answer*. This is the classic asymmetric query↔passage
mismatch of symmetric embedding models.

**What I changed to fix it (implemented + measured):** I added a **two-stage retrieval**
in `build_index.search()`: dense ANN pulls 40 candidates, then a **cross-encoder reranker**
(`cross-encoder/ms-marco-MiniLM-L-6-v2`) rescores each (query, chunk) pair *jointly* and
keeps the top 6. Because the cross-encoder reads the question and the review together, it
recognizes the review as the answer regardless of shared vocabulary. Measured: the
McAllister review went from **#9 → #1**, and the system now returns the correct cited
answer (and even flags from a later chunk that she has since left Minerva).

Notably, I first tried **BM25 and rejected it on evidence**: it ranked the review **#11**
(worse than dense), because "McAllister" recurs across many *question* chunks so the
keyword isn't discriminating. The same BM25 test, however, ranked the *"best healthcare
city"* answer **#1** (dense had it #3) — so hybrid BM25+dense is a justified **future add**
for exact-token queries (course codes, visa types, city names), just not the fix for this
particular failure. Lesson: match the tool to the failure mode — verify, don't assume.

---

## Spec Reflection

<!-- Reflect on how planning.md shaped your implementation.
     Answer both questions with at least 2–3 sentences each. -->

**One way the spec helped you during implementation:**

**One way your implementation diverged from the spec, and why:**

---

## AI Usage

<!-- Describe at least 2 specific instances where you used an AI tool during this project.
     For each: what did you give the AI as input, what did it produce, and what did you
     change, override, or direct differently?

     "I used Claude to help me code" is not sufficient.
     "I gave Claude my Chunking Strategy section from planning.md and asked it to implement
     chunk_text(). It returned a function using a fixed character split. I overrode the
     chunk size from 500 to 200 because my documents are short reviews, not long guides." -->

**Instance 1**

- *What I gave the AI:*
- *What it produced:*
- *What I changed or overrode:*

**Instance 2**

- *What I gave the AI:*
- *What it produced:*
- *What I changed or overrode:*
