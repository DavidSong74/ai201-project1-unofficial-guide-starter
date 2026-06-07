# Web interface — The Unofficial Guide to Minerva

React + Vite + Tailwind + shadcn/ui frontend (originally designed in Replit), wired to the
Python RAG pipeline via a small FastAPI backend.

## Architecture

```
web/ (Vite :5173)  --POST /ask-->  api.py (FastAPI :8000)
                                      └─ build_index.search()  (dense + cross-encoder rerank)
                                      └─ ask.generate()         (Groq, grounded)
```

Vite's dev server proxies `/ask` to `http://localhost:8000`, so the frontend fetches
same-origin. The single integration seam is `src/lib/askQuestion.ts` (it falls back to
mock data if the backend isn't running, so the UI still previews offline).

## Run (two terminals)

**1. Backend** (from the project root, with the venv active and `.env` holding `GROQ_API_KEY`):

```bash
pip install -r requirements.txt          # first time (adds fastapi + uvicorn)
uvicorn api:app --port 8000 --reload
```

**2. Frontend** (from `web/`):

```bash
npm install                              # first time
npm run dev                              # http://localhost:5173
```

Open http://localhost:5173 and ask a question. The chunk index must already be built
(`python scripts/build_index.py` → `chroma_db/`).

## Build for production

```bash
npm run build        # -> web/dist/  (static; serve behind / or from FastAPI)
```
