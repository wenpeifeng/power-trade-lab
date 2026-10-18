# ⚡ Power Trade Lab

> An open-source **Learn → Practice → Test → Simulate → Review** platform for China's electricity market.

English | **[简体中文](README.md)**

<p>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.141-009688?logo=fastapi&logoColor=white">
  <img alt="Vue" src="https://img.shields.io/badge/Vue-3-42B883?logo=vuedotjs&logoColor=white">
  <img alt="Vite" src="https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white">
  <img alt="Node" src="https://img.shields.io/badge/Node.js-22.12%2B-339933?logo=nodedotjs&logoColor=white">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-yellow.svg">
  <img alt="PRs welcome" src="https://img.shields.io/badge/PRs-welcome-5B67F1">
</p>

Electricity trading is not a stock terminal with power-industry vocabulary bolted on. Power Trade Lab combines market-learning materials, public-data ingestion, quizzes, exams, and two reproducible 24-period day-ahead teaching scenarios in a self-hostable full-stack application:

```text
Rules & real data → Knowledge base & courses → Quizzes & exams → Trading simulation → Settlement & review → Targeted re-learning ↺
```

> ⚠️ Power Trade Lab is **not** a licensed trading system and provides no investment advice. It is a teaching and research environment designed to make learning **explainable, reproducible, and traceable**.

## ✨ Highlights

- 🏠 **Personal portal** — learning path, skill progress, onboarding tasks, cross-system navigation
- 📚 **Learning center** — adaptive diagnosis, guided courses, free practice, spaced review of mistakes, exam prep
- 📄 **Textbook workshop** — PDF/Word import, MinerU-based Markdown conversion, chapter reading, notes
- 📊 **Trading simulation** — market data, bidding, positions, order book, full single-player scenarios, market clearing, settlement, and review
- 📢 **Policy tracker** — official announcements sorted by date, categorized by province, with source tracing
- 🔍 **Knowledge base** — category tree, multi-dimensional tagging, BM25 / semantic / hybrid retrieval
- 🗄️ **Data asset center** — multi-source ingestion, incremental crawling, deduplication, quality scoring, human review, asset timeline
- 🤖 **AI assistant (optional)** — per-user BYOK keys, answers grounded in the knowledge base
- 🌤️ **Weather integration (optional)** — QWeather live observations and hourly forecasts fed into the asset center

## 🧭 What makes it different

1. **Honest data provenance** — every market/simulation datum carries one of four source levels: `observed_public` / `observed_authorized` / `reconstructed` / `synthetic`. Reconstructed or synthetic data is **never** disguised as real-time market data.
2. **Replayable day-ahead scenarios** — the two single-player scenarios persist the rule version, inputs, random seed, bids, clearing, settlement, and review snapshots. The legacy terminal is outside this guarantee.
3. **Connected learning surfaces** — courses, quizzes, exams, materials, and simulation reviews live in one application. Automatic review-to-learning-plan write-back is still roadmap work.
4. **Zero-config start** — runs with no third-party API keys; AI, weather, and document parsing are all optional enhancements.
5. **BYOK by design** — each user supplies their own key, which is encrypted at rest in that deployment's database.

## 🚀 Quick Start

Requirements: macOS / Linux (WSL2 on Windows), Python 3.11/3.12, Node.js 22.12+, npm, and curl. Docker is not required.

```bash
git clone https://github.com/wenpeifeng/power-trade-lab.git
cd power-trade-lab

# Creates virtual environments and installs dependencies on first run
./script/sh/start-all.sh
```

- Web: <http://127.0.0.1:5173>
- API docs: <http://127.0.0.1:8000/docs>

Check with `./script/sh/status-all.sh` and stop with `./script/sh/stop-all.sh`. Register a normal account on first launch; the repository has no demo account or default password. Backend settings come from `backend/.env`, while optional frontend proxy settings come from `frontend/.env`. See the [configuration guide](docs/CONFIGURATION.md) (Chinese).

**Note:** the repository ships deterministic teaching seed records in source code, but no runtime database or user records. The seed is not a verified official dataset. Each deployment may ingest its own authorized data through the Data Asset Center. See the [data asset tools guide](docs/数据资产工具使用说明.md) (Chinese).

## 🧱 Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vue 3, Vite, Element Plus, ECharts, VueUse Motion |
| Backend | FastAPI, Pydantic, SQLAlchemy, APScheduler |
| Database | SQLite (the only ready-to-run path); PostgreSQL requires additional driver and migration work |
| Document parsing | pdfplumber + optional MinerU service |
| Retrieval | BM25, semantic vectors, hybrid search with optional reranking |
| Security | HttpOnly cookies, role-based access, per-user AI key encryption, outbound SSRF protection |

## 🗺️ Roadmap

- [ ] Provincial rule packages and real public market data
- [ ] 96-point multi-segment bidding with constraint validation and deterministic clearing
- [ ] Closing the loop: review weaknesses → recommended courses/quizzes → next simulation
- [ ] More scenarios: medium/long-term, spot, retail, ancillary services, green power & certificates
- [ ] A redistributable anonymized demo dataset
- [ ] Docker, PostgreSQL migrations, and multi-instance deployment

## 🤝 Contributing

Issues, provincial rule packages, question sources, and simulation improvements are all welcome. The UI, docs, and domain content are primarily in Chinese because the project targets China's electricity market — but code review, i18n, and English docs contributions are especially appreciated.

- 📋 [Contributing guide](CONTRIBUTING.md) (Chinese)
- 🔐 [Security policy](SECURITY.md)
- 🐛 [Issue templates](.github/ISSUE_TEMPLATE/)

If this project helps you, consider giving it a **Star** ⭐ — it helps more learners discover it and tells us which provinces and market products to prioritize next.

## 📄 License

[MIT](LICENSE)
