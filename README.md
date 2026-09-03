# Mise Waste Management RAG Assistant

An AI-powered question-answering assistant for Mise (the Aland waste management company) that answers questions about waste fees, sorting rules, opening hours, and forms, based on official PDF documents.

## Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Benchmark Results](#benchmark-results)
- [Features](#features)
- [CI/CD](#cicd)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [Postmortem & Engineering Challenges](#postmortem--engineering-challenges)
- [Known Limitations](#known-limitations)
- [Test Questions](#test-questions)
- [Roadmap](#roadmap)

## Overview

This project is a Retrieval-Augmented Generation (RAG) chatbot built to answer questions about Mise's waste fees and services in Swedish. The system retrieves relevant context from scanned and digital PDF documents (waste tariffs 2022–2026, sorting guides, forms) and generates answers using Google Gemini, citing the exact source document for each answer.

Live chatbot: https://mise-rag-project-by-me.streamlit.app/

Built with Streamlit, PostgreSQL + pgvector, and Google Gemini. Evaluated on a curated test set:

| Metric | Value |
| --- | --- |
| Keyword Hit Rate | **100% (5/5)** |
| p95 Latency | **~21,400 ms** (Neon cloud DB, no co-location) |
| Avg Latency | **~13,200 ms** |
| Avg Cost / Query | **$0.000324** |
| Repeat-query latency (cached) | **~0 ms / $0.00** via `@st.cache_data` |

The project handles several complex business rules, including:

- Different fees for private individuals versus businesses
- Different fees depending on whether the resident lives inside or outside Mise's member municipalities
- Price differences across tariff years (2022–2026)
- The distinction between Mise customers and non-Mise customers

## Architecture

The system consists of two main flows: an offline ingestion pipeline that prepares the documents, and an online query pipeline that answers user questions in real time.

```
PDF documents (waste tariffs, forms, sorting guides)
        |
        v
Ingestion: chunking + embedding (Gemini embedding-001)
  - pdfplumber extracts tables with [Rubrik: ...] section tags
  - Exponential backoff on 429 quota errors (up to 5 retries)
        |
        v
PostgreSQL 16 + pgvector
  - document_chunks: VECTOR(768), HNSW cosine index
  - forms_directory: GIN trigram index (pg_trgm)
        |
        v
User question
  --> @st.cache_data (TTL 1h): cache hit? return instantly at $0 cost
  --> cache miss: embed_query (Gemini embedding-001)
  --> retrieve_chunks (Top 12, recency-weighted: 2026 -0.15, 2025 -0.08)
  --> resolve_form() in parallel (trigram fuzzy match)
        |
        v
build_prompt (context + 6 deterministic business rules)
        |
        v
Gemini 3 Flash (generate_content, up to 3 retries on ServerError)
        |
        v
Answer with source citations + latency/cost metrics --> Streamlit UI
```

A separate module, `entity_resolver.py`, runs in parallel to identify whether the question matches a specific form (e.g. change of ownership, moving to a service residence).

## Benchmark Results

Evaluated on 2026-09-03 against a 5-query curated test set hitting the live Neon cloud PostgreSQL database.

| Query | Hit | Latency | Cost |
| --- | :---: | ---: | ---: |
| Scrap vehicle fee | PASS | 22,252 ms | $0.000280 |
| Refrigerator drop-off (private, no Misekort) | PASS | 17,869 ms | $0.000279 |
| Non-Mise municipality visit fee | PASS | 8,364 ms | $0.000277 |
| Waste sorting guide | PASS | 12,511 ms | $0.000477 |
| Library hours (out-of-scope guardrail) | PASS | 5,071 ms | $0.000306 |

| Metric | Value |
| --- | --- |
| **Hit Rate** | **100% (5/5)** |
| **p95 Latency** | **21,376 ms** |
| **Avg Latency** | **13,214 ms** |
| **Avg Cost / Query** | **$0.000324** |
| **Total Cost (5 queries)** | **$0.001619** |

> **Note on latency:** The high latency is expected in this dev setup — the Neon DB is hosted in `us-east-1` while the client runs locally in Europe, adding significant round-trip overhead. In a co-located production deployment, latency would drop substantially. Repeat queries for cached questions return in **~0 ms at $0 cost** via `@st.cache_data`.

Re-run the benchmark yourself:

```bash
python -m scripts.eval_benchmark
```

## Features

- Q&A in Swedish based solely on official Mise documents
- Automatic prioritization of the most recent tariff year (2026 > 2025 > older) when conflicting information exists
- Correct separation between private individual and business fees, only when they actually differ
- Terminology handling for concepts like "Ej verksamhetskund" (non-business customer) and "icke Misekunder" (non-Mise customers)
- Source citations in every answer, including the filename of the original document
- Form matching via `entity_resolver` (exact + fuzzy trigram match) for related paperwork
- Response caching via `@st.cache_data` (1-hour TTL): repeat queries cost $0 and return instantly
- Live latency and cost metrics displayed per answer in the Streamlit UI
- Automatic retry on temporary server errors (ServerError) from the Gemini API
- Guardrail against answering questions outside the knowledge base (e.g. library opening hours)
- Protection against inventing numeric limits that are not explicitly stated in the source material

## CI/CD

A GitHub Actions pipeline runs on every push and pull request to `main`:

- **Lint:** `flake8` checks for syntax errors and undefined names across `app/`, `scripts/`, and `tests/`
- **Import verification:** All core app modules (`config`, `entity_resolver`, `frontend`) are verified to parse without `ImportError`
- **Syntax checks:** `scripts/eval_benchmark.py` and all files in `tests/` are compiled with `py_compile` to catch regressions

See [`.github/workflows/ci.yml`](.github/workflows/ci.yml) for the full pipeline definition.

## Installation

### Prerequisites

- Python 3.10 or later
- PostgreSQL with the pgvector extension installed
- A valid Gemini API key

### Steps

1. Clone the repo:

```bash
git clone <repo-url>
cd Rag-for-Mise
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the project root:

```
GEMINI_API_KEY=your_api_key_here
DATABASE_URL=postgresql://user:password@localhost:5432/mise_rag
```

4. Set up the database and run the ingestion script to load the PDF documents.

## Configuration

All sensitive values (API keys, database connection) are loaded via the `.env` file using `python-dotenv`. Make sure `.env` is never committed to version control.

| Variable         | Description                                                |
| ---------------- | ---------------------------------------------------------- |
| `GEMINI_API_KEY` | API key for Google Gemini (embedding + generation)         |
| `DATABASE_URL`   | Connection string to the PostgreSQL database with pgvector |

## Usage

### Run via command line

```bash
python app/main.py
```

This runs through a predefined list of test questions in the `__main__` block.

### Run via Streamlit

```bash
streamlit run app/frontend.py
```

### Run benchmark

```bash
python -m scripts.eval_benchmark
```

### Programmatic usage

```python
from app.main import ask

answer = ask("Vad kostar det att lämna in ett kylskåp som privatperson utan Misekort?")
print(answer)
```

## Project Structure

```
Rag-for-Mise/
├── app/                          # Application source code
│   ├── main.py                   # Core RAG logic: embed, retrieve, prompt, generate
│   ├── frontend.py               # Streamlit UI with caching and metrics display
│   ├── config.py                 # Database connection helper
│   ├── entity_resolver.py        # Exact + fuzzy form matching via pg_trgm
│   └── __init__.py
│
├── scripts/                      # Data pipeline and evaluation scripts
│   ├── ingest_mise.py            # PDF ingestion pipeline with backoff retry
│   ├── eval_benchmark.py         # Benchmark: p95 latency, cost/query, hit rate
│   ├── mise_crawler.py           # Web scraper for mise.ax documents
│   ├── db_connector.py           # DB utility
│   ├── db/                       # Database inspection / maintenance scripts
│   │   ├── check_db.py           # Inspect [Rubrik] tags in chunks
│   │   ├── check_docs.py         # Search document chunks by keyword
│   │   ├── check_misekort.py     # Inspect Misekort-related chunks
│   │   ├── delete_docs.py        # Delete specific documents by ID
│   │   └── find_ids.py           # Lookup document IDs by filename pattern
│   └── __init__.py
│
├── db/                           # Database schema and backups
│   ├── init.sql                  # Schema: documents, document_chunks, forms_directory
│   └── mise_backup.dump          # PostgreSQL backup dump (gitignored)
│
├── tests/                        # Integration / smoke tests
│   ├── test_gemini.py            # Verify Gemini API key and embedding call
│   └── test_pdf.py               # Verify PDF table extraction from a sample file
│
├── .github/
│   └── workflows/
│       └── ci.yml                # GitHub Actions CI pipeline
│
├── mise-scraped-data/            # Raw scraped PDFs and pages (gitignored)
│   └── output/
│       ├── mise_pdfs/
│       ├── mise_pages/
│       └── mise_docs/
│
├── archive/                      # Archived / experimental files (gitignored)
│
├── docker-compose.yml            # Local PostgreSQL 16 + pgvector via Docker
├── requirements.txt              # Python dependencies
├── .env                          # Environment variables (gitignored)
├── .gitignore
└── README.md
```

## How It Works

### 1. Embedding and Storage

All PDF documents are split into smaller text chunks and converted into 768-dimensional vectors using the Gemini embedding-001 model. Each chunk is tagged with its source filename and, where possible, a "[Rubrik: ...]" (heading) tag indicating which document section the text came from.

### 2. Retrieval

When a user asks a question, it's converted into its own vector. The system retrieves the 12 most similar text chunks from the database, using a weighting that prioritizes newer documents (2026 gets a 0.15 boost, 2025 gets a 0.08 boost) to avoid surfacing outdated prices.

### 3. Prompt Construction

The retrieved chunks are combined with the user's question and six business rules, including:

- Always use the most recent year's price when conflicting information exists
- Never perform your own calculation of total prices
- Correctly distinguish household vs. business fees based on heading tags
- Correctly interpret "Ej verksamhetskund" and "icke Misekunder" based on the resident's municipality
- Only split the answer into Private/Business sections when fees actually differ
- Never invent specific numeric limits not explicitly stated in the source text

### 4. Generation

The final prompt is sent to Gemini 3 Flash, which generates an answer with source citations, with up to three retries on server overload.

### 5. Form Matching

`resolve_form()` runs in parallel to check whether the question relates to a specific form, giving the user a direct reference to the correct paperwork.

## 🛠️ Postmortem & Engineering Challenges

### 1. Multi-Year Tariff Price Collision
- **Issue:** High vector similarity between 2022 and 2026 tariff documents caused outdated 2022 prices to overrank and overwrite 2026 prices in generated answers.
- **Fix:** Implemented dynamic recency weighting directly in the PostgreSQL retrieval query, applying a subtracted score boost (`-0.15` for 2026 docs, `-0.08` for 2025 docs) at ORDER BY time — so newer documents rank higher without discarding older context.

### 2. Gemini API Rate Limiting (429 Quota Exhaustion During Ingestion)
- **Issue:** Batch document ingestion of 15+ PDFs repeatedly hit Gemini's embedding API rate limits mid-run, crashing the script and leaving the database in a partially ingested state.
- **Fix:** Engineered exponential backoff retry loops in `ingest_mise.py` that dynamically parse the `retryDelay` value from the API error response and pause execution for exactly that duration before retrying — with a max of 5 attempts per chunk.

### 3. Business vs. Private Fee Leakage (Wrong Fee Served to Wrong Customer)
- **Issue:** Chunk embeddings alone were insufficient to separate private household tariffs from commercial tariffs when the vector text was semantically similar. The model would occasionally serve a business fee to a private question.
- **Fix:** Enhanced the PDF table ingestion in `ingest_mise.py` with `pdfplumber` to prepend explicit `[Rubrik: ...]` section headers (extracted from numbered headings) to each table row chunk. Added deterministic prompt business rules instructing the model to trust `[Rubrik]` tags over raw similarity scores when assigning fees to household vs. business categories.

## Known Limitations

- Only answers based on ingested documentation, no external lookups
- Database must be updated manually when new tariff decisions are made
- Some older PDFs lack clear heading tags, which can rarely affect categorization
- Optimized for Swedish-language questions only

## Test Questions

| Question (Swedish) | Question (English) | Expected Answer |
| --- | --- | --- |
| Vad kostar det att lämna in ett kylskåp som privatperson utan Misekort? | Refrigerator drop-off, private person, no Mise card | 6.00 EUR (in Mise municipality) / 20.00 EUR (outside) |
| Jag bor inte i en Mise-kommun, vad kostar ett besök på återvinningscentralen? | Not living in a Mise municipality, recycling center cost | 20.00 EUR |
| Vad kostar det att slänga skrotfordon? | Cost to dispose of a scrap vehicle | 250.00 EUR (same for private/business) |
| Hur sorterar jag mitt avfall? | How to sort waste | List of categories: bio, combustible, cardboard, plastic, glass, metal |
| Hur anmäler jag ägarbyte? | How to report change of ownership | Reference to form, mail, or customer service |
| Vad är öppettiderna för biblioteket i Mariehamn? | Library opening hours in Mariehamn | "I don't know" (guardrail — outside knowledge base) |

## Future Work

Improved document tagging consistency — some older PDFs lack clear "[Rubrik: ...]" heading tags, which occasionally makes it harder to correctly separate household vs. business fees; standardizing tagging across all ingested documents (old and new) would remove this edge case entirely.

Multi-language support — the system currently only understands and answers in Swedish; adding English or Finnish support would make it usable for a wider range of residents and visitors.

Conversation memory / follow-up questions — right now each question is answered independently; adding session memory so users can ask natural follow-ups (e.g. "and what about businesses?") without repeating context would improve the user experience significantly.

Usage analytics and logging — tracking which questions are asked most often would help Mise identify gaps in their public documentation and prioritize which FAQs to clarify or expand.

Confidence scoring on answers — surfacing a visible indicator when the model has low retrieval confidence (e.g. few matching chunks) would help users know when to double-check with Mise directly instead of fully trusting the answer.

User feedback mechanism — a simple thumbs up/down on each answer would create a feedback loop to catch future hallucinations or outdated pricing before they spread.

Production-grade hosting — moving from Streamlit Community Cloud to a more robust setup (Docker + Railway/Render, or similar) if usage grows beyond a demo/pilot stage, to support more concurrent users reliably.

Admin dashboard for document management — a simple internal interface for Mise staff to upload new tariff PDFs themselves without needing a developer to manually run the ingestion script each time.

## Roadmap

- [x] Automated benchmark script for regression questions (`scripts/eval_benchmark.py`)
- [x] Response caching to eliminate repeat-query latency and cost
- [x] CI/CD pipeline via GitHub Actions
- [ ] Automated ingestion pipeline triggered on new tariff document uploads
- [ ] Extended support for more municipalities/languages
- [ ] Logging and analysis of common user questions
- [ ] Conversation memory for natural follow-up questions
