# MiniSearch

A small, honest search engine — with a dark, minimal, mobile-first web UI that also works great on tablet and desktop.

**Live site:** https://melleeyyy.github.io/minisearch/

This repo is the web frontend. The actual search happens in the [backend](https://github.com/melleeyyy/minisearch-core) — crawler, inverted index, BM25 ranking and C++ acceleration. The original Python engine that started the project is kept at [minisearch-engine](https://github.com/melleeyyy/minisearch-engine).

## What you can do

- **Web search** — BM25-ranked results with highlighted snippets, autocomplete suggestions, did-you-mean corrections and pagination.
- **Images** — the engine's own image index. Images are never re-hosted; each card links to the original image and its source page.
- **Videos** — proxied Wikimedia Commons video search.
- **Answers** — extractive question answering with confidence scores, citations and conflict warnings. No AI generation: answers are quoted word-for-word from indexed pages.
- **Status** — live engine info: index size, scoring engine, indexed sources.
- **Activity** — your recent searches (stored only on your device) plus anonymous engine analytics.

## Tech

Vite + React 18 + TypeScript. Hash-based routing, so deep links work on GitHub Pages. No UI framework — a single hand-written dark stylesheet (`src/styles/global.css`).

## Run it locally

```bash
npm install
npm run dev          # http://localhost:5173
npm run build        # type-check + production bundle in dist/
npm run preview      # serve the built site locally
```

The API base URL defaults to the live backend and can be overridden with `VITE_API_BASE` (see `.env.example`).

## Deployment

Every push to `main` builds and publishes to GitHub Pages via `.github/workflows/deploy.yml` (Pages source must be set to "GitHub Actions" in Settings → Pages).

---

*This repo was previously named `minisearch-frontend`. Old links and git remotes redirect automatically.*
