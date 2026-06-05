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
- The model only ever sees the **top-k retrieved chunks**, never the raw corpus.
- Each chunk is injected as a numbered, labelled block: `[n] Topic: <name> | <date>`
  followed by the messages — so the model can attribute claims to a specific source.
- A **relevance floor** drops any chunk below `MIN_SIM = 0.25` cosine similarity. If
  *nothing* clears the floor, `ask.py` short-circuits and prints "The chat doesn't have
  a clear answer on that" — the LLM is never invoked, so it cannot fall back on its own
  training knowledge.

**System prompt grounding instruction (verbatim, abridged):**
> You answer using ONLY the numbered context below… Do not use outside knowledge. Cite
> every claim with the source number(s) in square brackets, e.g. [2]. If the context does
> not contain the answer, say so plainly: "The chat doesn't have a clear answer on that."
> Do not guess or invent details. These are individual student opinions and may be
> outdated or contradictory — when sources disagree, say so.

**How source attribution is surfaced in the response:** the model cites inline `[n]`
markers, and `ask.py` prints a `Sources:` list mapping each `[n]` → `topic | date (sim)`.
Verified working: e.g. *"How have students gotten an O-1 visa?"* returned an answer
citing a Dyer Harris law-firm thread [3] and an O-1/EB-1 webinar [2], each traceable to a
dated Visas-topic chunk. The refusal path is also verified — when the actual answer chunk
isn't retrieved, the model says so instead of fabricating (see Failure Case Analysis).

---

## Evaluation Report

<!-- Run your 5 test questions from planning.md through your system and record the results.
     Be honest — a partially accurate or inaccurate result that you explain well is more
     valuable than a suspiciously perfect result. -->

| # | Question | Expected answer | System response (summarized) | Retrieval quality | Response accuracy |
|---|----------|-----------------|------------------------------|-------------------|-------------------|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |
| 5 | | | | | |

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

**What you would change to fix it:**
1. Use an **asymmetric retrieval model** with query/passage prefixes (e.g. `bge-*` with
   `"query:"` / `"passage:"`, or an instruction-tuned embedder) so questions align to
   answers instead of to other questions.
2. Add **hybrid retrieval** — a BM25 keyword pass alongside the dense one. "McAllister" is
   a rare, high-signal token; lexical search would rank the review near the top regardless
   of phrasing, then fuse with dense scores (RRF).
3. Cheap stopgap: raise k (the chunk is at #9, so k≥9 retrieves it) and/or apply MMR to
   demote near-duplicate question chunks so distinct answers get a slot.

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
