# AI-Powered Psychographic Lead Intelligence Platform

An AI-powered platform that identifies and ranks leads based on psychographic profiling — going beyond demographics to understand *why* people buy products.

## How It Works

1. A company submits a product and target location
2. The system generates buyer motivation categories using Llama 3.1
3. Public social media content is discovered and collected
4. An NLP pipeline extracts personality signals from the content
5. OCEAN personality scores are generated for each discovered user
6. A matching engine scores and ranks users by compatibility
7. Ranked leads are displayed in a dashboard

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI · Python 3.11 |
| Database | PostgreSQL · pgvector |
| ORM | SQLAlchemy 2.0 (async) |
| LLM | Ollama · Llama 3.1 8B |
| NLP | Sentence Transformers · Empath · BERTopic · spaCy |
| Frontend | Next.js (Sprint 3+) |
| Hosting | Railway · Vercel · Oracle Free Tier |

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── dependencies.py
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── crud/
│   │   ├── routers/
│   │   ├── services/
│   │   └── ml/
│   ├── requirements.txt
│   └── .env.example
├── IMPLEMENTATION_PLAN.md
└── SPRINT_BACKLOG.md
```

## Local Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt

cp .env.example .env
# Edit .env with your DATABASE_URL and OLLAMA_BASE_URL

uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in your values.

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (`postgresql+asyncpg://...`) |
| `OLLAMA_BASE_URL` | Ollama server URL (`http://localhost:11434`) |
| `OLLAMA_MODEL` | Model name (`llama3.1:8b`) |
| `ENVIRONMENT` | `development` or `production` |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/api/v1/companies` | Register company, receive API key |
| GET | `/api/v1/companies` | List companies |
| POST | `/api/v1/products` | Submit product, trigger motivation generation |
| GET | `/api/v1/products` | List products |
| GET | `/api/v1/products/{id}` | Get product + pipeline status |
| GET | `/api/v1/products/{id}/motivations` | Get generated motivation categories |
