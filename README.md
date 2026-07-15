# Mise Waste Management RAG Assistant

An AI-powered question-answering assistant for Mise (the Aland waste management company) that answers questions about waste fees, sorting rules, opening hours, and forms, based on official PDF documents.

## Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [Known Limitations](#known-limitations)
- [Test Questions](#test-questions)
- [Roadmap](#roadmap)

## Overview

This project is a Retrieval-Augmented Generation (RAG) chatbot built to answer questions about Mise's waste fees and services in Swedish. The system retrieves relevant context from scanned and digital PDF documents (waste tariffs 2022-2026, sorting guides, forms) and generates answers using Google Gemini, citing the exact source document for each answer.

The project handles several complex business rules, including:

- Different fees for private individuals versus businesses
- Different fees depending on whether the resident lives inside or outside Mise's member municipalities
- Price differences across tariff years (2022-2026)
- The distinction between Mise customers and non-Mise customers

## Architecture

The system consists of two main flows: an offline ingestion pipeline that prepares the documents, and an online query pipeline that answers user questions in real time.

```
PDF documents (waste tariffs, forms, sorting guides)
        |
        v
Ingestion: chunking + embedding (Gemini embedding-001)
        |
        v
PostgreSQL + pgvector (document_chunks table)
        |
        v
User question --> embed_query --> retrieve_chunks (top 12, year-weighted ranking)
        |
        v
build_prompt (context + 6 business rules)
        |
        v
Gemini 3 Flash (generate_content)
        |
        v
Answer with source citations --> Streamlit UI
```

A separate module, `entity_resolver.py`, runs in parallel to identify whether the question matches a specific form (e.g. change of ownership, moving to a service residence).

## Features

- Q&A in Swedish based solely on official Mise documents
- Automatic prioritization of the most recent tariff year (2026 > 2025 > older) when conflicting information exists
- Correct separation between private individual and business fees, only when they actually differ
- Terminology handling for concepts like "Ej verksamhetskund" (non-business customer) and "icke Misekunder" (non-Mise customers)
- Source citations in every answer, including the filename of the original document
- Form matching via `entity_resolver` for related paperwork
- Automatic retry on temporary server errors (ServerError) from the Gemini API
- Guardrail against answering questions outside the knowledge base (e.g. library opening hours)
- Protection against inventing numeric limits that are not explicitly stated in the source material

## Installation

### Prerequisites

- Python 3.10 or later
- PostgreSQL with the pgvector extension installed
- A valid Gemini API key

### Steps

1. Clone the repo:

```bash
git clone <repo-url>
cd rag
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
python main.py
```

This runs through a predefined list of test questions in the `__main__` block.

### Run via Streamlit

```bash
streamlit run main.py
```

### Programmatic usage

```python
from main import ask

answer = ask("Vad kostar det att lämna in ett kylskåp som privatperson utan Misekort?")
print(answer)
```

## Project Structure

```
rag/
├── main.py                  # Core logic: embedding, retrieval, prompt, generation
├── app/
│   ├── config.py             # Database connection
│   └── entity_resolver.py    # Matching against relevant forms
├── check_docs.py             # Verification script to search document_chunks
├── requirements.txt
├── .env                      # Environment variables (not in version control)
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

## Known Limitations

- Only answers based on ingested documentation, no external lookups
- Database must be updated manually when new tariff decisions are made
- Some older PDFs lack clear heading tags, which can rarely affect categorization
- Optimized for Swedish-language questions only

## Test Questions

| Question                                                       | Expected Answer                                                        |
| -------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Refrigerator drop-off, private person, no Mise card            | 6.00 EUR (in Mise municipality) / 20.00 EUR (outside)                  |
| Not living in a Mise municipality, recycling center visit cost | 20.00 EUR                                                              |
| Cost to dispose of a scrap vehicle                             | 250.00 EUR (same for private/business, no split)                       |
| How to sort waste                                              | List of categories: bio, combustible, cardboard, plastic, glass, metal |
| How to report change of ownership                              | Reference to form, mail, or customer service                           |
| Library opening hours in Mariehamn                             | "I don't know" (guardrail, outside knowledge base)                     |

| Question                                                                      | Expected Answer                                                        |
| ----------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Vad kostar det att lämna in ett kylskåp som privatperson utan Misekort?       | 6.00 EUR (in Mise municipality) / 20.00 EUR (outside)                  |
| Jag bor inte i en Mise-kommun, vad kostar ett besök på återvinningscentralen? | 20.00 EUR                                                              |
| Vad kostar det att slänga skrotfordon?                                        | 250.00 EUR (same for private/business, no split)                       |
| Hur sorterar jag mitt avfall?                                                 | List of categories: bio, combustible, cardboard, plastic, glass, metal |
| Hur anmäler jag ägarbyte?                                                     | Reference to form, mail, or customer service                           |
| Vad är öppettiderna för biblioteket i Mariehamn?                              | "I don't know" (guardrail, outside knowledge base)                     |

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

- [ ] Automated test script for regression questions
- [ ] Automated ingestion pipeline for new tariff documents
- [ ] Extended support for more municipalities/languages
- [ ] Logging and analysis of common user questions
