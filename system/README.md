# OPTIONAL — demonstration system

**Nothing in this directory is required to reproduce any quantitative result in
the article.** Every number in Sects. 6.1–6.13 comes from the reference estimator
in `../evaluation/` and the campaign records in `../realworld/`.

This directory is included only because Table 2 of the article ("Implementation
status of IncidentMind components") makes checkable claims about the
demonstration system, and a reader auditing that table should be able to see it:

| Table 2 claim | Where to check |
|---|---|
| Five source types normalised into a common schema; 325 records in the bundled corpus | `datasets/` (24 alerts + 50 commits + 10 deployments + 204 logs + 37 chat messages), `incidentmind-data/` |
| `all-MiniLM-L6-v2` sentence-transformer (384-d) via `@xenova/transformers`, indexed in ChromaDB | `server/rag/embed.js` |
| Dense retrieval of top-30 candidates, typed re-ranking, returning top-10 | `server/rag/retrieve-semantic-v2.js` |
| Deterministic breadth-first forward traversal, no LLM involvement | `server/blast-radius/calculate.js` |
| React/Vite single-page application, React Flow dependency graph, Socket.IO telemetry | `frontend/` |
| Dashboard what-if panel and recovery-recommendation panel are **illustrative only** (status **D**) | `frontend/src/components/ParallelSimulator.jsx`, `server/recovery/calculate.js` |

Status labels in Table 2: **I** implemented and exercised end-to-end, **P**
prototype, **D** illustrative only and part of no evaluated result.

## Corpus provenance

`datasets/` and `incidentmind-data/` are **synthetic**, produced by
`datasets/generate_evidence.js`. Personas (`alice`, `bob`, `charlie`) are
fictional. No real organisation's operational data is included.

## Running it (not needed for the article)

```bash
npm install
node server.js          # http://localhost:3000
cd frontend && npm install && npm run dev
```

Two server routes (`server/rca/`, `server/ask-incidentmind/`) can call the
OpenRouter API and read `OPENROUTER_API_KEY` from the environment; both fall back
to deterministic, evidence-based generation when the variable is unset. No key is
included in this repository, and no result in the article depends on those routes.
