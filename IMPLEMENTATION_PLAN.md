# AI-Powered Psychographic Lead Intelligence Platform
## Developer-Ready Implementation Document

---

## Table of Contents

1. [Database Schema & Tables](#1-database-schema--tables)
2. [Backend Architecture](#2-backend-architecture)
3. [Frontend Architecture](#3-frontend-architecture)
4. [Folder Structure](#4-folder-structure)
5. [API Design](#5-api-design)
6. [Module: Product Profiling](#6-module-product-profiling)
7. [Module: Motivation Category Generation](#7-module-motivation-category-generation)
8. [Module: User Discovery](#8-module-user-discovery)
9. [Module: NLP Pipeline](#9-module-nlp-pipeline)
10. [Module: OCEAN Scoring](#10-module-ocean-scoring)
11. [Module: Matching Engine](#11-module-matching-engine)
12. [Module: Lead Ranking](#12-module-lead-ranking)
13. [Module: Dashboard](#13-module-dashboard)
14. [Week-by-Week Roadmap](#14-week-by-week-roadmap)
15. [Development Order](#15-development-order)
16. [MVP Scope](#16-mvp-scope)
17. [Deployment Plan](#17-deployment-plan)
18. [Testing Strategy](#18-testing-strategy)

---

## 1. Database Schema & Tables

### Overview

All data lives in PostgreSQL. Vector data uses the `pgvector` extension. Every UUID is generated with `gen_random_uuid()`. Timestamps are `TIMESTAMPTZ` defaulting to `NOW()`.

### Enable Extensions

```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
```

---

### Table 1: `companies`

**Purpose:** Stores company accounts that use the platform.

```sql
CREATE TABLE companies (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          VARCHAR(255) NOT NULL,
    email         VARCHAR(255) UNIQUE NOT NULL,
    industry      VARCHAR(100),
    website       VARCHAR(500),
    description   TEXT,
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_companies_email ON companies(email);
```

---

### Table 2: `products`

**Purpose:** Each product submitted by a company. This is the entry point for the entire pipeline.

```sql
CREATE TYPE product_status AS ENUM (
    'pending',
    'analyzing',
    'motivations_generated',
    'discovering',
    'nlp_processing',
    'ocean_scoring',
    'matching',
    'ranked',
    'completed',
    'failed'
);

CREATE TYPE price_range AS ENUM (
    'budget',
    'mid_range',
    'premium',
    'luxury'
);

CREATE TABLE products (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name             VARCHAR(255) NOT NULL,
    description      TEXT NOT NULL,
    category         VARCHAR(100) NOT NULL,
    subcategory      VARCHAR(100),
    price_range      price_range NOT NULL,
    target_location  VARCHAR(255) NOT NULL,
    target_city      VARCHAR(100),
    target_country   VARCHAR(100) DEFAULT 'India',
    keywords         JSONB DEFAULT '[]',
    status           product_status DEFAULT 'pending',
    pipeline_step    INTEGER DEFAULT 0,
    error_message    TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_products_company_id ON products(company_id);
CREATE INDEX idx_products_status ON products(status);
```

---

### Table 3: `motivation_categories`

**Purpose:** LLM-generated motivation categories explaining WHY people buy a product. One product has 4-6 categories.

```sql
CREATE TABLE motivation_categories (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id      UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    description     TEXT NOT NULL,
    weight          FLOAT DEFAULT 1.0,
    embedding       VECTOR(384),
    sort_order      INTEGER DEFAULT 0,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_motivation_categories_product_id ON motivation_categories(product_id);
CREATE INDEX idx_motivation_categories_embedding ON motivation_categories
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);
```

---

### Table 4: `motivation_ocean_profiles`

**Purpose:** Expected OCEAN personality profile and interest/keyword signals for each motivation category.

```sql
CREATE TABLE motivation_ocean_profiles (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    motivation_category_id   UUID NOT NULL REFERENCES motivation_categories(id) ON DELETE CASCADE,
    openness                 FLOAT NOT NULL CHECK (openness BETWEEN 0 AND 10),
    conscientiousness        FLOAT NOT NULL CHECK (conscientiousness BETWEEN 0 AND 10),
    extraversion             FLOAT NOT NULL CHECK (extraversion BETWEEN 0 AND 10),
    agreeableness            FLOAT NOT NULL CHECK (agreeableness BETWEEN 0 AND 10),
    emotional_stability      FLOAT NOT NULL CHECK (emotional_stability BETWEEN 0 AND 10),
    interest_tags            JSONB DEFAULT '[]',
    search_keywords          JSONB DEFAULT '[]',
    hashtags                 JSONB DEFAULT '[]',
    created_at               TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_motivation_ocean_profiles_category_id
    ON motivation_ocean_profiles(motivation_category_id);
```

---

### Table 5: `discovery_jobs`

**Purpose:** Tracks each lead discovery job associated with a product. A product can have multiple discovery runs.

```sql
CREATE TYPE job_status AS ENUM (
    'queued', 'running', 'paused', 'completed', 'failed'
);

CREATE TABLE discovery_jobs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id          UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    status              job_status DEFAULT 'queued',
    sources             JSONB DEFAULT '["reddit", "twitter"]',
    search_config       JSONB NOT NULL,
    users_discovered    INTEGER DEFAULT 0,
    users_processed     INTEGER DEFAULT 0,
    error_message       TEXT,
    celery_task_id      VARCHAR(255),
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_discovery_jobs_product_id ON discovery_jobs(product_id);
CREATE INDEX idx_discovery_jobs_status ON discovery_jobs(status);
```

---

### Table 6: `discovered_users`

**Purpose:** Stores discovered social media profiles. One record per unique user per discovery job.

```sql
CREATE TYPE social_platform AS ENUM (
    'reddit', 'twitter', 'instagram', 'linkedin', 'mock'
);

CREATE TABLE discovered_users (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    discovery_job_id   UUID NOT NULL REFERENCES discovery_jobs(id) ON DELETE CASCADE,
    product_id         UUID NOT NULL REFERENCES products(id),
    platform           social_platform NOT NULL,
    platform_user_id   VARCHAR(255),
    username           VARCHAR(255) NOT NULL,
    display_name       VARCHAR(255),
    bio                TEXT,
    location           VARCHAR(255),
    follower_count     INTEGER DEFAULT 0,
    following_count    INTEGER DEFAULT 0,
    post_count         INTEGER DEFAULT 0,
    profile_url        VARCHAR(1000),
    raw_profile        JSONB DEFAULT '{}',
    content_collected  BOOLEAN DEFAULT FALSE,
    nlp_processed      BOOLEAN DEFAULT FALSE,
    ocean_scored       BOOLEAN DEFAULT FALSE,
    matched            BOOLEAN DEFAULT FALSE,
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(platform, platform_user_id, discovery_job_id)
);

CREATE INDEX idx_discovered_users_job_id ON discovered_users(discovery_job_id);
CREATE INDEX idx_discovered_users_product_id ON discovered_users(product_id);
CREATE INDEX idx_discovered_users_content_collected ON discovered_users(content_collected);
CREATE INDEX idx_discovered_users_nlp_processed ON discovered_users(nlp_processed);
CREATE INDEX idx_discovered_users_ocean_scored ON discovered_users(ocean_scored);
```

---

### Table 7: `user_content`

**Purpose:** Stores raw content collected from each discovered user (posts, captions, comments, bio, hashtags).

```sql
CREATE TYPE content_type AS ENUM (
    'bio', 'post', 'caption', 'comment', 'hashtag', 'about'
);

CREATE TABLE user_content (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES discovered_users(id) ON DELETE CASCADE,
    content_type  content_type NOT NULL,
    content_text  TEXT NOT NULL,
    source_url    VARCHAR(1000),
    platform      social_platform,
    engagement    INTEGER DEFAULT 0,
    posted_at     TIMESTAMPTZ,
    collected_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_user_content_user_id ON user_content(user_id);
CREATE INDEX idx_user_content_type ON user_content(content_type);
CREATE INDEX idx_user_content_text_gin ON user_content USING gin(to_tsvector('english', content_text));
```

---

### Table 8: `user_embeddings`

**Purpose:** Stores sentence transformer vector embeddings for each user. Used in similarity matching.

```sql
CREATE TYPE embedding_type AS ENUM (
    'combined', 'bio', 'posts', 'comments', 'topics'
);

CREATE TABLE user_embeddings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES discovered_users(id) ON DELETE CASCADE,
    embedding_type  embedding_type NOT NULL,
    embedding       VECTOR(384) NOT NULL,
    model_used      VARCHAR(100) DEFAULT 'all-MiniLM-L6-v2',
    token_count     INTEGER,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, embedding_type)
);

CREATE INDEX idx_user_embeddings_user_id ON user_embeddings(user_id);
CREATE INDEX idx_user_embeddings_combined ON user_embeddings(user_id)
    WHERE embedding_type = 'combined';
CREATE INDEX idx_user_embeddings_vector ON user_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

---

### Table 9: `user_nlp_features`

**Purpose:** Stores extracted NLP features: Empath scores, BERTopic topics, spaCy entities, linguistic features.

```sql
CREATE TABLE user_nlp_features (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL REFERENCES discovered_users(id) ON DELETE CASCADE,
    empath_scores        JSONB DEFAULT '{}',
    bertopic_topics      JSONB DEFAULT '[]',
    bertopic_probs       JSONB DEFAULT '[]',
    spacy_entities       JSONB DEFAULT '[]',
    sentiment_score      FLOAT,
    sentiment_label      VARCHAR(20),
    interest_tags        JSONB DEFAULT '[]',
    keyword_frequency    JSONB DEFAULT '{}',
    vocabulary_richness  FLOAT,
    avg_sentence_length  FLOAT,
    total_tokens         INTEGER DEFAULT 0,
    linguistic_features  JSONB DEFAULT '{}',
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id)
);

CREATE INDEX idx_user_nlp_features_user_id ON user_nlp_features(user_id);
CREATE INDEX idx_user_nlp_features_interest_tags ON user_nlp_features USING gin(interest_tags);
```

---

### Table 10: `user_ocean_scores`

**Purpose:** Stores LLM-generated OCEAN personality scores for each user.

```sql
CREATE TABLE user_ocean_scores (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL REFERENCES discovered_users(id) ON DELETE CASCADE,
    openness             FLOAT NOT NULL CHECK (openness BETWEEN 0 AND 10),
    conscientiousness    FLOAT NOT NULL CHECK (conscientiousness BETWEEN 0 AND 10),
    extraversion         FLOAT NOT NULL CHECK (extraversion BETWEEN 0 AND 10),
    agreeableness        FLOAT NOT NULL CHECK (agreeableness BETWEEN 0 AND 10),
    emotional_stability  FLOAT NOT NULL CHECK (emotional_stability BETWEEN 0 AND 10),
    confidence_score     FLOAT CHECK (confidence_score BETWEEN 0 AND 1),
    llm_reasoning        TEXT,
    prompt_tokens        INTEGER,
    completion_tokens    INTEGER,
    model_used           VARCHAR(100) DEFAULT 'llama3.1:8b',
    scored_at            TIMESTAMPTZ DEFAULT NOW(),
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id)
);

CREATE INDEX idx_user_ocean_scores_user_id ON user_ocean_scores(user_id);
CREATE INDEX idx_user_ocean_scores_openness ON user_ocean_scores(openness);
CREATE INDEX idx_user_ocean_scores_extraversion ON user_ocean_scores(extraversion);
```

---

### Table 11: `lead_matches`

**Purpose:** Scores each discovered user against each motivation category. One row per (user, category) pair.

```sql
CREATE TABLE lead_matches (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                   UUID NOT NULL REFERENCES discovered_users(id) ON DELETE CASCADE,
    motivation_category_id    UUID NOT NULL REFERENCES motivation_categories(id) ON DELETE CASCADE,
    product_id                UUID NOT NULL REFERENCES products(id),
    personality_match_score   FLOAT CHECK (personality_match_score BETWEEN 0 AND 1),
    interest_match_score      FLOAT CHECK (interest_match_score BETWEEN 0 AND 1),
    activity_score            FLOAT CHECK (activity_score BETWEEN 0 AND 1),
    confidence_score          FLOAT CHECK (confidence_score BETWEEN 0 AND 1),
    compatibility_score       FLOAT CHECK (compatibility_score BETWEEN 0 AND 1),
    match_details             JSONB DEFAULT '{}',
    created_at                TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, motivation_category_id)
);

CREATE INDEX idx_lead_matches_user_id ON lead_matches(user_id);
CREATE INDEX idx_lead_matches_product_id ON lead_matches(product_id);
CREATE INDEX idx_lead_matches_motivation_category_id ON lead_matches(motivation_category_id);
CREATE INDEX idx_lead_matches_compatibility_score ON lead_matches(compatibility_score DESC);
```

---

### Table 12: `leads`

**Purpose:** Final ranked lead list per product. One row per (user, product) pair, using their best motivation category match.

```sql
CREATE TYPE lead_tier AS ENUM ('hot', 'warm', 'cold');

CREATE TYPE lead_status AS ENUM (
    'new', 'viewed', 'contacted', 'converted', 'rejected'
);

CREATE TABLE leads (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id                  UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    user_id                     UUID NOT NULL REFERENCES discovered_users(id) ON DELETE CASCADE,
    best_motivation_category_id UUID REFERENCES motivation_categories(id),
    rank                        INTEGER NOT NULL,
    compatibility_score         FLOAT NOT NULL,
    tier                        lead_tier NOT NULL,
    status                      lead_status DEFAULT 'new',
    notes                       TEXT,
    created_at                  TIMESTAMPTZ DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(product_id, user_id)
);

CREATE INDEX idx_leads_product_id ON leads(product_id);
CREATE INDEX idx_leads_rank ON leads(product_id, rank);
CREATE INDEX idx_leads_tier ON leads(product_id, tier);
CREATE INDEX idx_leads_compatibility_score ON leads(compatibility_score DESC);
```

---

### Entity Relationship Summary

```
companies (1) ──── (many) products
products  (1) ──── (many) motivation_categories
motivation_categories (1) ──── (1) motivation_ocean_profiles
products  (1) ──── (many) discovery_jobs
discovery_jobs (1) ──── (many) discovered_users
products  (1) ──── (many) discovered_users
discovered_users (1) ──── (many) user_content
discovered_users (1) ──── (many) user_embeddings
discovered_users (1) ──── (1)    user_nlp_features
discovered_users (1) ──── (1)    user_ocean_scores
discovered_users (1) ──── (many) lead_matches ──── (many) motivation_categories
discovered_users (1) ──── (1)    leads (per product)
```

---

## 2. Backend Architecture

### Architecture Style

Event-driven, pipeline-based monolith with async background tasks. Not microservices — single FastAPI app with Celery workers. This is MVP-appropriate and deployable on Railway in one service.

```
Client (Next.js)
      │
      ▼
FastAPI (HTTP Layer)
  ├── Routers (API handlers)
  ├── Services (Business logic)
  ├── ML Modules (NLP + LLM)
  └── Workers (Celery background tasks)
      │
      ▼
PostgreSQL + pgvector
      │
Redis (Celery broker + cache)
      │
Ollama (Llama 3.1 8B — on Oracle VM)
```

### Key Design Principles

- **Pipeline trigger model:** Every pipeline step is a Celery task. Steps chain automatically.
- **Idempotency:** Every task checks if its work is already done before running.
- **Status tracking:** Each product has a `status` and `pipeline_step` column updated after each step.
- **Batch processing:** NLP and OCEAN scoring process users in batches of 20 to avoid memory pressure.

### Technology Versions

```
Python             3.11+
FastAPI            0.110+
SQLAlchemy         2.0+ (async)
Celery             5.3+
Redis              7.x
sentence-transformers  2.7+
spacy              3.7+
bertopic           0.16+
empath             0.89+
ollama (python)    0.2+
pgvector           0.2+
alembic            1.13+
```

---

## 3. Frontend Architecture

### Architecture Style

Next.js 14+ App Router with server components for data fetching and client components for interactivity.

```
Next.js App
  ├── App Router (layouts, pages)
  ├── Server Components (data fetching via API)
  ├── Client Components (charts, forms, real-time polling)
  ├── React Query (client-side cache + polling)
  ├── Zustand (global UI state)
  └── shadcn/ui + Tailwind (component library)
```

### Real-time Updates

Use **polling** (React Query with `refetchInterval`) for pipeline status. No WebSockets needed for MVP. Poll every 5 seconds when a job is running.

### Key UI Libraries

```
next                14.x
react               18.x
tailwindcss         3.x
shadcn/ui           latest
@tanstack/react-query  5.x
zustand             4.x
recharts            2.x (OCEAN radar chart, bar charts)
lucide-react        (icons)
axios               (API calls)
```

---

## 4. Folder Structure

### Backend

```
backend/
├── app/
│   ├── main.py                    ← FastAPI app init, middleware, router mounts
│   ├── config.py                  ← Pydantic settings from .env
│   ├── database.py                ← SQLAlchemy async engine, session factory
│   │
│   ├── models/                    ← SQLAlchemy ORM models (one file per table group)
│   │   ├── __init__.py
│   │   ├── company.py             ← Company
│   │   ├── product.py             ← Product
│   │   ├── motivation.py          ← MotivationCategory, MotivationOceanProfile
│   │   ├── discovery.py           ← DiscoveryJob
│   │   ├── user.py                ← DiscoveredUser, UserContent
│   │   ├── nlp.py                 ← UserEmbedding, UserNlpFeatures
│   │   ├── ocean.py               ← UserOceanScore
│   │   └── lead.py                ← LeadMatch, Lead
│   │
│   ├── schemas/                   ← Pydantic request/response schemas
│   │   ├── __init__.py
│   │   ├── company.py
│   │   ├── product.py
│   │   ├── motivation.py
│   │   ├── discovery.py
│   │   ├── user.py
│   │   ├── lead.py
│   │   └── dashboard.py
│   │
│   ├── routers/                   ← FastAPI routers (HTTP handlers only)
│   │   ├── __init__.py
│   │   ├── companies.py
│   │   ├── products.py
│   │   ├── motivations.py
│   │   ├── discovery.py
│   │   ├── users.py
│   │   ├── leads.py
│   │   └── dashboard.py
│   │
│   ├── services/                  ← Business logic (call ML modules, write DB)
│   │   ├── __init__.py
│   │   ├── company_service.py
│   │   ├── product_service.py
│   │   ├── motivation_service.py
│   │   ├── discovery_service.py
│   │   ├── content_service.py
│   │   ├── nlp_service.py
│   │   ├── ocean_service.py
│   │   ├── matching_service.py
│   │   └── lead_service.py
│   │
│   ├── ml/                        ← Pure ML/AI modules (no DB access)
│   │   ├── __init__.py
│   │   ├── embeddings.py          ← SentenceTransformer wrapper
│   │   ├── empath_analyzer.py     ← Empath wrapper
│   │   ├── bertopic_modeler.py    ← BERTopic wrapper
│   │   ├── spacy_processor.py     ← spaCy wrapper
│   │   ├── llm_client.py          ← Ollama HTTP client wrapper
│   │   ├── ocean_prompter.py      ← OCEAN prompt builder and parser
│   │   └── motivation_prompter.py ← Motivation generation prompt builder
│   │
│   ├── workers/                   ← Celery task definitions
│   │   ├── celery_app.py          ← Celery app instance, Redis broker config
│   │   └── tasks/
│   │       ├── __init__.py
│   │       ├── product_tasks.py   ← analyze_product, generate_motivations
│   │       ├── discovery_tasks.py ← run_discovery, collect_content
│   │       ├── nlp_tasks.py       ← process_user_nlp (batch)
│   │       ├── scoring_tasks.py   ← score_user_ocean (batch)
│   │       └── matching_tasks.py  ← match_users, rank_leads
│   │
│   └── utils/
│       ├── __init__.py
│       ├── text_cleaner.py        ← Remove URLs, normalize text
│       ├── location_utils.py      ← Location normalization
│       └── rate_limiter.py        ← API rate limiting helpers
│
├── migrations/
│   ├── env.py
│   └── versions/
│       ├── 001_initial_schema.py
│       ├── 002_add_pgvector.py
│       └── 003_add_indexes.py
│
├── tests/
│   ├── unit/
│   │   ├── test_motivation_prompter.py
│   │   ├── test_ocean_prompter.py
│   │   ├── test_matching_engine.py
│   │   └── test_text_cleaner.py
│   ├── integration/
│   │   ├── test_product_pipeline.py
│   │   ├── test_nlp_pipeline.py
│   │   └── test_api_endpoints.py
│   └── fixtures/
│       ├── mock_users.json
│       └── mock_ocean_responses.json
│
├── .env.example
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── alembic.ini
```

### Frontend

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx                      ← Root layout, providers
│   │   ├── page.tsx                        ← Landing page
│   │   ├── globals.css
│   │   │
│   │   ├── (auth)/
│   │   │   ├── login/page.tsx
│   │   │   └── register/page.tsx
│   │   │
│   │   └── dashboard/
│   │       ├── layout.tsx                  ← Sidebar + header shell
│   │       ├── page.tsx                    ← Overview dashboard
│   │       │
│   │       ├── products/
│   │       │   ├── page.tsx                ← Product list
│   │       │   ├── new/page.tsx            ← Submit new product
│   │       │   └── [id]/
│   │       │       ├── page.tsx            ← Product overview + pipeline status
│   │       │       ├── motivations/page.tsx← View motivation categories + OCEAN
│   │       │       ├── discovery/page.tsx  ← Discovery job status + user list
│   │       │       ├── leads/page.tsx      ← Ranked leads table
│   │       │       └── analytics/page.tsx  ← Charts and stats
│   │
│   ├── components/
│   │   ├── ui/                             ← shadcn generated components
│   │   │
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx
│   │   │   ├── Header.tsx
│   │   │   └── PipelineStatusBadge.tsx
│   │   │
│   │   ├── products/
│   │   │   ├── ProductForm.tsx             ← Multi-step product submission form
│   │   │   ├── ProductCard.tsx
│   │   │   └── PipelineTracker.tsx         ← Visual step-by-step status
│   │   │
│   │   ├── motivations/
│   │   │   ├── MotivationCard.tsx          ← Category card with OCEAN scores
│   │   │   └── OceanRadarChart.tsx         ← Recharts RadarChart for OCEAN
│   │   │
│   │   ├── discovery/
│   │   │   ├── DiscoveryProgress.tsx       ← Live progress bar + user count
│   │   │   └── DiscoveredUserRow.tsx
│   │   │
│   │   ├── leads/
│   │   │   ├── LeadsTable.tsx              ← Sortable, filterable leads table
│   │   │   ├── LeadDrawer.tsx              ← Side panel: full profile + scores
│   │   │   ├── TierBadge.tsx               ← Hot / Warm / Cold badge
│   │   │   └── CompatibilityGauge.tsx
│   │   │
│   │   └── dashboard/
│   │       ├── StatsCards.tsx
│   │       ├── TopLeadsWidget.tsx
│   │       └── RecentActivityFeed.tsx
│   │
│   ├── lib/
│   │   ├── api.ts                          ← axios instance + all API functions
│   │   ├── utils.ts                        ← cn(), formatters
│   │   └── hooks/
│   │       ├── useProduct.ts
│   │       ├── useLeads.ts
│   │       ├── useDiscovery.ts
│   │       └── usePipelineStatus.ts        ← Polls until status = completed
│   │
│   ├── types/
│   │   ├── product.ts
│   │   ├── motivation.ts
│   │   ├── user.ts
│   │   ├── lead.ts
│   │   └── dashboard.ts
│   │
│   └── store/
│       └── useAppStore.ts                  ← Zustand: selected product, filters
│
├── public/
├── tailwind.config.ts
├── next.config.ts
├── tsconfig.json
├── package.json
└── Dockerfile
```

---

## 5. API Design

### Base URL: `/api/v1`

### Authentication

MVP: API key in header (`X-API-Key`). The company's API key is generated on registration.

```
X-API-Key: <company_api_key>
```

---

### Companies

```
POST   /companies                     Register company, returns API key
GET    /companies/me                  Get current company profile
PATCH  /companies/me                  Update company profile
```

---

### Products

```
POST   /products                      Submit new product → triggers pipeline
GET    /products                      List all products for this company
GET    /products/{id}                 Get product + current pipeline status
GET    /products/{id}/status          Lightweight poll endpoint (status + step only)
PATCH  /products/{id}                 Update product metadata
DELETE /products/{id}                 Delete product + all associated data
POST   /products/{id}/restart         Restart pipeline from failed step
```

**POST /products request body:**
```json
{
  "name": "Premium Sofa",
  "description": "A premium 3-seater sofa with Italian leather...",
  "category": "Furniture",
  "subcategory": "Sofas",
  "price_range": "premium",
  "target_location": "Chennai",
  "keywords": ["sofa", "furniture", "home decor"]
}
```

**GET /products/{id} response:**
```json
{
  "id": "uuid",
  "name": "Premium Sofa",
  "status": "matching",
  "pipeline_step": 6,
  "motivation_categories_count": 5,
  "users_discovered": 284,
  "users_scored": 241,
  "leads_count": 50,
  "created_at": "2026-06-01T10:00:00Z"
}
```

---

### Motivation Categories

```
GET    /products/{id}/motivations                    List all motivation categories
POST   /products/{id}/motivations/regenerate         Force regenerate motivation categories
GET    /products/{id}/motivations/{m_id}             Get single motivation + OCEAN profile
PATCH  /products/{id}/motivations/{m_id}             Update name/description/weight
DELETE /products/{id}/motivations/{m_id}             Remove a motivation category
```

**GET /products/{id}/motivations response:**
```json
{
  "product_id": "uuid",
  "categories": [
    {
      "id": "uuid",
      "name": "Aesthetic / Interior Design Focus",
      "description": "Buyers who purchase for visual appeal...",
      "weight": 1.0,
      "ocean_profile": {
        "openness": 8.5,
        "conscientiousness": 6.0,
        "extraversion": 6.5,
        "agreeableness": 6.0,
        "emotional_stability": 6.5
      },
      "interest_tags": ["interior design", "home decor", "architecture"],
      "search_keywords": ["home decor", "interior", "aesthetic"],
      "hashtags": ["#interiordesign", "#homedecor", "#aesthetic"]
    }
  ]
}
```

---

### Discovery

```
POST   /products/{id}/discovery/start               Start a new discovery job
GET    /products/{id}/discovery/jobs                List all discovery jobs for product
GET    /products/{id}/discovery/jobs/{job_id}       Get job details + progress
POST   /products/{id}/discovery/jobs/{job_id}/stop  Stop running job
GET    /products/{id}/discovery/users               List discovered users (paginated)
GET    /products/{id}/discovery/users/{user_id}     Get single user + all content
```

**POST /products/{id}/discovery/start request:**
```json
{
  "sources": ["reddit", "twitter"],
  "max_users": 500,
  "search_config": {
    "location": "Chennai",
    "interest_keywords": ["home decor", "interior design", "luxury living"],
    "hashtags": ["#homedecor", "#interiordesign"]
  }
}
```

---

### NLP & Scoring (Internal trigger, also exposable)

```
POST   /products/{id}/pipeline/run-nlp        Trigger NLP for all unprocessed users
POST   /products/{id}/pipeline/run-ocean      Trigger OCEAN scoring for NLP-done users
POST   /products/{id}/pipeline/run-matching   Trigger matching engine
GET    /products/{id}/pipeline/logs           Get task execution logs
```

---

### Leads

```
GET    /products/{id}/leads                   Get ranked leads (paginated, filterable)
GET    /products/{id}/leads/{lead_id}         Get full lead profile
PATCH  /products/{id}/leads/{lead_id}         Update lead status (viewed/contacted/etc)
GET    /products/{id}/leads/export            Export leads as CSV
GET    /products/{id}/leads/stats             Tier distribution, score histogram
```

**GET /products/{id}/leads query params:**
```
?tier=hot&status=new&min_score=0.6&page=1&limit=20&sort=rank
```

**GET /products/{id}/leads response:**
```json
{
  "total": 284,
  "page": 1,
  "limit": 20,
  "leads": [
    {
      "rank": 1,
      "user": {
        "username": "interiorfan_chennai",
        "platform": "reddit",
        "bio": "Interior design lover from Chennai...",
        "follower_count": 3200
      },
      "best_motivation": "Aesthetic / Interior Design Focus",
      "compatibility_score": 0.87,
      "tier": "hot",
      "ocean": {
        "openness": 8.2,
        "conscientiousness": 6.1,
        "extraversion": 7.0,
        "agreeableness": 6.3,
        "emotional_stability": 6.0
      },
      "status": "new"
    }
  ]
}
```

---

### Dashboard

```
GET    /dashboard/overview             Summary: products, leads, pipeline health
GET    /dashboard/recent-activity      Recent jobs, leads, pipeline events
GET    /dashboard/top-leads            Top 10 leads across all products
```

---

## 6. Module: Product Profiling

### What to Build

A service that receives the company's product submission and prepares it for the pipeline. Immediately triggers motivation category generation as a Celery task.

### Why It Exists

The product is the entry point. Everything downstream — discovery filters, OCEAN targets, matching — is shaped by the product. We need a clean, enriched product record before any ML work begins.

### Inputs

- Company ID (from API key)
- Product name, description, category, price range
- Target location

### Outputs

- Product record saved to `products` table
- Celery task ID for motivation generation
- Product status: `analyzing`

### Implementation

**`app/services/product_service.py`**
```python
from app.models.product import Product
from app.workers.tasks.product_tasks import generate_motivations_task
from app.schemas.product import ProductCreate
from sqlalchemy.ext.asyncio import AsyncSession

async def create_product(db: AsyncSession, company_id: str, data: ProductCreate) -> Product:
    product = Product(
        company_id=company_id,
        name=data.name,
        description=data.description,
        category=data.category,
        subcategory=data.subcategory,
        price_range=data.price_range,
        target_location=data.target_location,
        target_city=extract_city(data.target_location),
        keywords=data.keywords,
        status="analyzing"
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)

    # Fire-and-forget Celery task
    generate_motivations_task.delay(str(product.id))

    return product
```

### Tables Involved

- `products` (write)

### APIs Involved

- `POST /products`

---

## 7. Module: Motivation Category Generation

### What to Build

A Celery task that calls Llama 3.1 via Ollama with a structured prompt to generate 4-6 motivation categories for a product. Parses the JSON response and stores categories with OCEAN profiles and embeddings.

### Why It Exists

Motivation categories replace generic OCEAN targeting. They answer "WHY does someone buy this?" and let us create multiple buyer personas with distinct OCEAN signatures for the same product.

### Inputs

- Product record (name, description, category, price range)

### Outputs

- 4-6 `motivation_categories` rows
- 4-6 `motivation_ocean_profiles` rows (one per category)
- Sentence transformer embedding per category (stored in `motivation_categories.embedding`)

### Implementation

**`app/ml/motivation_prompter.py`**
```python
MOTIVATION_SYSTEM_PROMPT = """You are an expert psychographic marketing strategist.
Your job is to identify the psychological motivations behind product purchases.
Always respond with valid JSON only. No explanation text outside the JSON."""

def build_motivation_prompt(product: dict) -> str:
    return f"""
Analyze this product and generate exactly 5 distinct motivation categories.
Each category represents a different psychological reason WHY someone would buy this product.

Product Name: {product['name']}
Category: {product['category']}
Price Range: {product['price_range']}
Description: {product['description']}

For each motivation category, provide:
- name: short category name (5-7 words max)
- description: 2-3 sentence explanation of this buyer type
- ocean: expected Big Five scores (0-10 each)
  - openness: curiosity, creativity, aesthetic appreciation
  - conscientiousness: organization, discipline, planning
  - extraversion: sociability, enthusiasm, visibility-seeking
  - agreeableness: cooperation, warmth, community-focus
  - emotional_stability: calmness, resilience (high = stable)
- interest_tags: list of 5-8 interest areas this buyer likely has
- search_keywords: list of 8-12 keywords they would use in posts/captions
- hashtags: list of 6-10 hashtags they would use

Return ONLY this JSON structure:
{{
  "motivation_categories": [
    {{
      "name": "string",
      "description": "string",
      "ocean": {{
        "openness": float,
        "conscientiousness": float,
        "extraversion": float,
        "agreeableness": float,
        "emotional_stability": float
      }},
      "interest_tags": ["string"],
      "search_keywords": ["string"],
      "hashtags": ["string"]
    }}
  ]
}}
"""
```

**`app/workers/tasks/product_tasks.py`**
```python
from app.workers.celery_app import celery
from app.ml.llm_client import OllamaClient
from app.ml.motivation_prompter import build_motivation_prompt
from app.ml.embeddings import EmbeddingModel
from app.database import get_sync_session
from app.models.motivation import MotivationCategory, MotivationOceanProfile
from app.models.product import Product
import json

@celery.task(bind=True, max_retries=3, name="tasks.generate_motivations")
def generate_motivations_task(self, product_id: str):
    with get_sync_session() as db:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return

        try:
            # Build prompt
            llm = OllamaClient()
            embedder = EmbeddingModel()
            prompt = build_motivation_prompt(product.__dict__)

            # Call Llama 3.1
            response = llm.generate(
                model="llama3.1:8b",
                system=MOTIVATION_SYSTEM_PROMPT,
                prompt=prompt,
                temperature=0.3,
                format="json"
            )

            data = json.loads(response["response"])
            categories = data["motivation_categories"]

            # Persist each category
            for i, cat in enumerate(categories):
                # Generate embedding for category description
                embedding = embedder.encode(
                    f"{cat['name']} {cat['description']} {' '.join(cat['interest_tags'])}"
                )

                mc = MotivationCategory(
                    product_id=product_id,
                    name=cat["name"],
                    description=cat["description"],
                    embedding=embedding.tolist(),
                    sort_order=i
                )
                db.add(mc)
                db.flush()

                ocean_profile = MotivationOceanProfile(
                    motivation_category_id=mc.id,
                    openness=cat["ocean"]["openness"],
                    conscientiousness=cat["ocean"]["conscientiousness"],
                    extraversion=cat["ocean"]["extraversion"],
                    agreeableness=cat["ocean"]["agreeableness"],
                    emotional_stability=cat["ocean"]["emotional_stability"],
                    interest_tags=cat["interest_tags"],
                    search_keywords=cat["search_keywords"],
                    hashtags=cat["hashtags"]
                )
                db.add(ocean_profile)

            product.status = "motivations_generated"
            product.pipeline_step = 2
            db.commit()

        except Exception as exc:
            product.status = "failed"
            product.error_message = str(exc)
            db.commit()
            raise self.retry(exc=exc, countdown=60)
```

### Tables Involved

- `products` (read + status update)
- `motivation_categories` (write)
- `motivation_ocean_profiles` (write)

### APIs Involved

- `GET /products/{id}/motivations`
- `POST /products/{id}/motivations/regenerate`

---

## 8. Module: User Discovery

### What to Build

A Celery task that searches public social media sources for users matching the product's keywords, location, and interest profile. Stores raw profiles in `discovered_users` and triggers content collection.

### Why It Exists

We need users whose publicly available content can be analyzed. Discovery is the top of the funnel — we cast a wide net here and narrow it through NLP and OCEAN scoring.

### Inputs

- Product ID
- Discovery job config: sources, max_users, keywords, location, hashtags

### Outputs

- `discovery_jobs` row (tracking)
- Multiple `discovered_users` rows
- Triggers content collection per user

### Sources (MVP)

**Reddit (via PRAW — free, no login required for public posts):**
- Search subreddits relevant to the product category
- Find users who posted in those subreddits
- Filter by location mentions in bio/flair

**Mock Source (for dev/testing):**
- JSON fixture of 500 realistic fake profiles
- Used when real API keys are unavailable

### Implementation

**`app/ml/discovery/reddit_discoverer.py`**
```python
import praw
from app.config import settings

class RedditDiscoverer:
    def __init__(self):
        self.reddit = praw.Reddit(
            client_id=settings.REDDIT_CLIENT_ID,
            client_secret=settings.REDDIT_CLIENT_SECRET,
            user_agent="PsychographicLeads/1.0"
        )

    def discover_users(self, keywords: list[str], subreddits: list[str],
                       location: str, max_users: int = 200) -> list[dict]:
        discovered = {}

        for subreddit_name in subreddits:
            try:
                subreddit = self.reddit.subreddit(subreddit_name)
                for keyword in keywords[:3]:  # limit to 3 keywords per subreddit
                    for submission in subreddit.search(keyword, limit=50, sort="relevance"):
                        author = submission.author
                        if author and str(author) not in discovered:
                            profile = self._extract_profile(author)
                            if profile:
                                discovered[str(author)] = profile
                        if len(discovered) >= max_users:
                            break
            except Exception:
                continue

        return list(discovered.values())

    def _extract_profile(self, author) -> dict | None:
        try:
            return {
                "platform": "reddit",
                "platform_user_id": str(author.id),
                "username": str(author.name),
                "display_name": str(author.name),
                "bio": getattr(author, 'subreddit', {}).get('public_description', ''),
                "follower_count": getattr(author, 'link_karma', 0),
                "following_count": 0,
                "post_count": getattr(author, 'num_posts', 0),
                "profile_url": f"https://reddit.com/u/{author.name}",
                "raw_profile": {}
            }
        except Exception:
            return None
```

**`app/services/discovery_service.py`**
```python
async def start_discovery(db: AsyncSession, product_id: str, config: dict) -> DiscoveryJob:
    job = DiscoveryJob(
        product_id=product_id,
        sources=config.get("sources", ["reddit"]),
        search_config=config,
        status="queued"
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    run_discovery_task.delay(str(job.id))
    return job
```

**`app/workers/tasks/discovery_tasks.py`**
```python
@celery.task(bind=True, name="tasks.run_discovery")
def run_discovery_task(self, job_id: str):
    with get_sync_session() as db:
        job = db.query(DiscoveryJob).filter(DiscoveryJob.id == job_id).first()
        product = job.product
        job.status = "running"
        job.started_at = datetime.utcnow()
        db.commit()

        try:
            # Get search config from motivation categories
            all_keywords = []
            all_hashtags = []
            all_interests = []

            for category in product.motivation_categories:
                profile = category.ocean_profile
                all_keywords.extend(profile.search_keywords)
                all_hashtags.extend(profile.hashtags)
                all_interests.extend(profile.interest_tags)

            # Deduplicate
            keywords = list(set(all_keywords))[:15]

            # Map category to subreddits
            subreddits = map_keywords_to_subreddits(all_interests)

            discoverer = RedditDiscoverer()
            users = discoverer.discover_users(
                keywords=keywords,
                subreddits=subreddits,
                location=product.target_city,
                max_users=job.search_config.get("max_users", 300)
            )

            # Bulk insert discovered users
            for user_data in users:
                user = DiscoveredUser(
                    discovery_job_id=job_id,
                    product_id=product.id,
                    **user_data
                )
                db.merge(user)

            job.users_discovered = len(users)
            job.status = "completed"
            job.completed_at = datetime.utcnow()

            product.status = "discovering"
            product.pipeline_step = 3
            db.commit()

            # Trigger content collection
            collect_content_task.delay(job_id)

        except Exception as exc:
            job.status = "failed"
            job.error_message = str(exc)
            db.commit()
            raise
```

### Tables Involved

- `discovery_jobs` (write + status update)
- `discovered_users` (bulk write)
- `products` (status update)

### APIs Involved

- `POST /products/{id}/discovery/start`
- `GET /products/{id}/discovery/jobs/{job_id}`

---

## 9. Module: NLP Pipeline

### What to Build

A Celery task that processes each discovered user's collected content through four NLP tools in sequence, then stores results in `user_embeddings` and `user_nlp_features`.

### Why It Exists

Raw text cannot be compared to OCEAN profiles. NLP converts text into structured signals — embeddings, topics, emotional categories, linguistic features — that feed the OCEAN scorer and matching engine.

### Inputs

- `user_id` for a single user
- All `user_content` rows for that user

### Outputs

- 1 row in `user_embeddings` (combined embedding)
- 1 row in `user_nlp_features`
- `discovered_users.nlp_processed = true`

### Implementation

**`app/ml/embeddings.py`**
```python
from sentence_transformers import SentenceTransformer
import numpy as np

class EmbeddingModel:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.model = SentenceTransformer('all-MiniLM-L6-v2')
        return cls._instance

    def encode(self, text: str) -> np.ndarray:
        return self.model.encode(text, normalize_embeddings=True)

    def encode_batch(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, normalize_embeddings=True, batch_size=32)
```

**`app/ml/empath_analyzer.py`**
```python
from empath import Empath

class EmpathAnalyzer:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.lexicon = Empath()
        return cls._instance

    def analyze(self, text: str) -> dict:
        scores = self.lexicon.analyze(text, normalize=True)
        # Filter out zero-score categories for storage efficiency
        return {k: v for k, v in scores.items() if v and v > 0.001}

    def get_top_categories(self, scores: dict, n: int = 15) -> list[tuple]:
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:n]
```

**`app/ml/bertopic_modeler.py`**
```python
from bertopic import BERTopic
from sentence_transformers import SentenceTransformer

class TopicModeler:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            cls._instance.model = BERTopic(
                embedding_model=embedding_model,
                min_topic_size=2,
                verbose=False
            )
            cls._instance.fitted = False
        return cls._instance

    def get_topics(self, texts: list[str]) -> list[dict]:
        if len(texts) < 2:
            return []
        try:
            topics, probs = self.model.fit_transform(texts)
            topic_info = self.model.get_topic_info()
            return [
                {"topic_id": int(t), "probability": float(p)}
                for t, p in zip(topics, probs)
            ]
        except Exception:
            return []
```

**`app/ml/spacy_processor.py`**
```python
import spacy

class SpacyProcessor:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.nlp = spacy.load('en_core_web_sm',
                disable=['parser', 'ner'])
            cls._instance.ner = spacy.load('en_core_web_sm',
                disable=['tagger', 'lemmatizer'])
        return cls._instance

    def extract_features(self, text: str) -> dict:
        doc = self.nlp(text)
        ner_doc = self.ner(text[:50000])  # cap at 50k chars

        tokens = [t for t in doc if not t.is_stop and not t.is_punct]
        sentences = list(doc.sents)

        return {
            "entities": [
                {"text": ent.text, "label": ent.label_}
                for ent in ner_doc.ents
            ],
            "vocabulary_richness": len(set(t.lemma_ for t in tokens)) / max(len(tokens), 1),
            "avg_sentence_length": sum(len(list(s)) for s in sentences) / max(len(sentences), 1),
            "total_tokens": len(tokens)
        }
```

**`app/services/nlp_service.py`**
```python
from app.ml.embeddings import EmbeddingModel
from app.ml.empath_analyzer import EmpathAnalyzer
from app.ml.bertopic_modeler import TopicModeler
from app.ml.spacy_processor import SpacyProcessor
from app.utils.text_cleaner import clean_text

async def process_user_nlp(db: AsyncSession, user_id: str):
    user = await db.get(DiscoveredUser, user_id)
    contents = await get_user_content(db, user_id)

    if not contents:
        return

    # Combine all text
    bio_text = user.bio or ""
    post_texts = [c.content_text for c in contents if c.content_type in ("post", "caption")]
    all_texts = [bio_text] + post_texts
    combined_text = clean_text(" ".join(all_texts))

    if not combined_text.strip():
        return

    # 1. Sentence Transformer embedding
    embedder = EmbeddingModel()
    embedding = embedder.encode(combined_text)

    ue = UserEmbedding(
        user_id=user_id,
        embedding_type="combined",
        embedding=embedding.tolist(),
        token_count=len(combined_text.split())
    )
    db.add(ue)

    # 2. Empath scores
    empath = EmpathAnalyzer()
    empath_scores = empath.analyze(combined_text)

    # 3. BERTopic
    topic_model = TopicModeler()
    topics = topic_model.get_topics(post_texts if len(post_texts) >= 2 else [combined_text])

    # 4. spaCy features
    spacy_proc = SpacyProcessor()
    spacy_features = spacy_proc.extract_features(combined_text)

    # 5. Interest tag extraction from Empath top categories
    top_empath = empath.get_top_categories(empath_scores, n=10)
    interest_tags = [cat for cat, _ in top_empath]

    nlp_features = UserNlpFeatures(
        user_id=user_id,
        empath_scores=empath_scores,
        bertopic_topics=topics,
        spacy_entities=spacy_features["entities"],
        interest_tags=interest_tags,
        vocabulary_richness=spacy_features["vocabulary_richness"],
        avg_sentence_length=spacy_features["avg_sentence_length"],
        total_tokens=spacy_features["total_tokens"]
    )
    db.add(nlp_features)

    user.nlp_processed = True
    await db.commit()
```

### Tables Involved

- `user_content` (read)
- `user_embeddings` (write)
- `user_nlp_features` (write)
- `discovered_users` (update `nlp_processed`)

---

## 10. Module: OCEAN Scoring

### What to Build

A Celery task that takes a user's NLP features and raw content, builds a structured prompt, calls Llama 3.1 via Ollama, parses the JSON response, and stores the OCEAN scores.

### Why It Exists

OCEAN scores are the core psychographic signal. They convert qualitative text into quantitative personality dimensions that can be mathematically compared to the target profiles.

### Inputs

- User ID
- `user_nlp_features` for that user
- Up to 10 recent posts/captions from `user_content`
- User bio

### Outputs

- 1 row in `user_ocean_scores`
- `discovered_users.ocean_scored = true`

### Implementation

**`app/ml/ocean_prompter.py`**
```python
OCEAN_SYSTEM = """You are a psychographic analyst specializing in the Big Five personality model.
You infer personality traits from public social media behavior.
You always respond with valid JSON only. Be calibrated and avoid extreme scores."""

def build_ocean_prompt(user_data: dict) -> str:
    bio = user_data.get("bio", "No bio available")
    posts = user_data.get("posts", [])[:8]
    posts_str = "\n".join([f"- {p}" for p in posts]) if posts else "No posts available"
    top_empath = user_data.get("top_empath_categories", [])
    empath_str = ", ".join([f"{k}({v:.2f})" for k, v in top_empath])
    interest_tags = ", ".join(user_data.get("interest_tags", []))

    return f"""
Analyze this person's public social media content and generate their Big Five (OCEAN) personality scores.

--- PROFILE ---
Bio: {bio}

Recent Posts/Captions:
{posts_str}

Detected Emotional/Interest Categories (Empath): {empath_str}
Extracted Interest Tags: {interest_tags}

--- SCORING GUIDE ---
Score each dimension from 0 to 10:

Openness (0=routine/conventional, 10=curious/creative/aesthetic)
Conscientiousness (0=spontaneous/disorganized, 10=disciplined/planned/detail-oriented)
Extraversion (0=introverted/quiet, 10=social/assertive/expressive)
Agreeableness (0=competitive/skeptical, 10=cooperative/trusting/empathetic)
Emotional Stability (0=anxious/reactive, 10=calm/resilient/stable)

Confidence: How confident are you in this assessment? (0.0 to 1.0)
Use 0.3-0.5 for sparse content, 0.6-0.8 for moderate content, 0.8+ for rich content.

--- OUTPUT ---
Return ONLY this exact JSON:
{{
  "openness": <float 0-10>,
  "conscientiousness": <float 0-10>,
  "extraversion": <float 0-10>,
  "agreeableness": <float 0-10>,
  "emotional_stability": <float 0-10>,
  "confidence": <float 0-1>,
  "reasoning": "<one paragraph explaining the key signals that drove these scores>"
}}
"""

def parse_ocean_response(response_text: str) -> dict | None:
    import json, re
    # Extract JSON from response
    match = re.search(r'\{.*\}', response_text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
        required = ["openness", "conscientiousness", "extraversion",
                    "agreeableness", "emotional_stability", "confidence"]
        if not all(k in data for k in required):
            return None
        # Clamp all scores to valid range
        for key in required[:-1]:  # all except confidence
            data[key] = max(0.0, min(10.0, float(data[key])))
        data["confidence"] = max(0.0, min(1.0, float(data["confidence"])))
        return data
    except (json.JSONDecodeError, ValueError):
        return None
```

**`app/ml/llm_client.py`**
```python
import httpx
from app.config import settings

class OllamaClient:
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL  # e.g. http://oracle-vm-ip:11434
        self.timeout = 120.0

    def generate(self, model: str, system: str, prompt: str,
                 temperature: float = 0.2, format: str = "json") -> dict:
        payload = {
            "model": model,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": 500,
                "top_p": 0.9
            },
            "format": format if format == "json" else None
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{self.base_url}/api/generate", json=payload)
            response.raise_for_status()
            return response.json()
```

**`app/workers/tasks/scoring_tasks.py`**
```python
@celery.task(bind=True, name="tasks.score_ocean_batch")
def score_ocean_batch_task(self, product_id: str, batch_size: int = 10):
    with get_sync_session() as db:
        users = (db.query(DiscoveredUser)
                   .filter(
                       DiscoveredUser.product_id == product_id,
                       DiscoveredUser.nlp_processed == True,
                       DiscoveredUser.ocean_scored == False
                   )
                   .limit(batch_size)
                   .all())

        if not users:
            # All done — trigger matching
            run_matching_task.delay(product_id)
            return

        for user in users:
            try:
                score_single_user(db, user)
            except Exception as e:
                continue  # skip individual failures

        # Re-queue for next batch
        score_ocean_batch_task.apply_async(
            args=[product_id, batch_size],
            countdown=5
        )

def score_single_user(db, user: DiscoveredUser):
    nlp = db.query(UserNlpFeatures).filter(
        UserNlpFeatures.user_id == user.id).first()
    contents = (db.query(UserContent)
                  .filter(UserContent.user_id == user.id,
                          UserContent.content_type.in_(["post", "caption"]))
                  .order_by(UserContent.collected_at.desc())
                  .limit(8)
                  .all())

    user_data = {
        "bio": user.bio,
        "posts": [c.content_text[:300] for c in contents],
        "top_empath_categories": list(nlp.empath_scores.items())[:10] if nlp else [],
        "interest_tags": nlp.interest_tags[:8] if nlp else []
    }

    llm = OllamaClient()
    prompt = build_ocean_prompt(user_data)
    raw = llm.generate("llama3.1:8b", OCEAN_SYSTEM, prompt)
    result = parse_ocean_response(raw["response"])

    if result:
        score = UserOceanScore(
            user_id=user.id,
            openness=result["openness"],
            conscientiousness=result["conscientiousness"],
            extraversion=result["extraversion"],
            agreeableness=result["agreeableness"],
            emotional_stability=result["emotional_stability"],
            confidence_score=result["confidence"],
            llm_reasoning=result.get("reasoning", ""),
            model_used="llama3.1:8b"
        )
        db.add(score)
        user.ocean_scored = True
        db.commit()
```

### Tables Involved

- `user_nlp_features` (read)
- `user_content` (read)
- `discovered_users` (read + update `ocean_scored`)
- `user_ocean_scores` (write)

---

## 11. Module: Matching Engine

### What to Build

A service that computes a 4-component compatibility score between each discovered user and each motivation category for a product. Stores one `lead_matches` row per (user, category) pair.

### Why It Exists

A user is a potential lead not because they exist — but because their personality and interests align with the psychological profile of a buyer type. The matching engine quantifies this alignment.

### Inputs

- All `discovered_users` where `ocean_scored = true` for a product
- All `motivation_categories` + `motivation_ocean_profiles` for that product
- `user_ocean_scores`, `user_embeddings`, `user_nlp_features` for each user

### Outputs

- N × M rows in `lead_matches` (N users × M motivation categories)

### Score Components

| Component | Weight | How Calculated |
|---|---|---|
| Personality Match | 40% | Normalized OCEAN distance in 5D space |
| Interest Match | 35% | Cosine similarity (user embedding vs category embedding) |
| Activity Score | 15% | Normalized follower count + post frequency |
| Confidence Score | 10% | LLM confidence from OCEAN scoring |

### Implementation

**`app/services/matching_service.py`**
```python
import numpy as np
from math import sqrt

OCEAN_DIMENSIONS = ["openness", "conscientiousness", "extraversion",
                     "agreeableness", "emotional_stability"]
MAX_OCEAN_DISTANCE = sqrt(5 * 100)  # max possible = sqrt(5 * 10^2) ≈ 22.36

def calculate_personality_match(user_ocean: dict, target_ocean: dict) -> float:
    squared_diffs = sum(
        (user_ocean[d] - target_ocean[d]) ** 2
        for d in OCEAN_DIMENSIONS
    )
    distance = sqrt(squared_diffs)
    return round(1.0 - (distance / MAX_OCEAN_DISTANCE), 4)

def calculate_interest_match(user_embedding: list, category_embedding: list) -> float:
    u = np.array(user_embedding)
    c = np.array(category_embedding)
    # Embeddings are already L2-normalized, so dot product = cosine similarity
    score = float(np.dot(u, c))
    # Cosine similarity range [-1, 1] → normalize to [0, 1]
    return round((score + 1.0) / 2.0, 4)

def calculate_activity_score(user: dict) -> float:
    # Normalize follower count (log scale, cap at 100k)
    followers = min(user.get("follower_count", 0), 100_000)
    follower_score = np.log1p(followers) / np.log1p(100_000)

    # Post count signal
    posts = min(user.get("post_count", 0), 10_000)
    post_score = np.log1p(posts) / np.log1p(10_000)

    return round((follower_score * 0.6 + post_score * 0.4), 4)

def calculate_compatibility(
    personality_match: float,
    interest_match: float,
    activity_score: float,
    confidence: float
) -> float:
    return round(
        personality_match * 0.40 +
        interest_match   * 0.35 +
        activity_score   * 0.15 +
        confidence       * 0.10,
        4
    )
```

**`app/workers/tasks/matching_tasks.py`**
```python
@celery.task(name="tasks.run_matching")
def run_matching_task(product_id: str):
    with get_sync_session() as db:
        product = db.query(Product).get(product_id)
        categories = product.motivation_categories

        users = (db.query(DiscoveredUser)
                   .filter(
                       DiscoveredUser.product_id == product_id,
                       DiscoveredUser.ocean_scored == True
                   )
                   .all())

        product.status = "matching"
        db.commit()

        for user in users:
            ocean = db.query(UserOceanScore).filter_by(user_id=user.id).first()
            embedding = (db.query(UserEmbedding)
                           .filter_by(user_id=user.id, embedding_type="combined")
                           .first())

            if not ocean or not embedding:
                continue

            for category in categories:
                profile = category.ocean_profile
                if not profile or not category.embedding:
                    continue

                target_ocean = {
                    "openness": profile.openness,
                    "conscientiousness": profile.conscientiousness,
                    "extraversion": profile.extraversion,
                    "agreeableness": profile.agreeableness,
                    "emotional_stability": profile.emotional_stability
                }
                user_ocean = {
                    "openness": ocean.openness,
                    "conscientiousness": ocean.conscientiousness,
                    "extraversion": ocean.extraversion,
                    "agreeableness": ocean.agreeableness,
                    "emotional_stability": ocean.emotional_stability
                }

                personality_score = calculate_personality_match(user_ocean, target_ocean)
                interest_score = calculate_interest_match(embedding.embedding, category.embedding)
                activity = calculate_activity_score(user.__dict__)
                compat = calculate_compatibility(
                    personality_score, interest_score,
                    activity, ocean.confidence_score
                )

                match = LeadMatch(
                    user_id=user.id,
                    motivation_category_id=category.id,
                    product_id=product_id,
                    personality_match_score=personality_score,
                    interest_match_score=interest_score,
                    activity_score=activity,
                    confidence_score=ocean.confidence_score,
                    compatibility_score=compat,
                    match_details={
                        "personality_weight": 0.40,
                        "interest_weight": 0.35,
                        "activity_weight": 0.15,
                        "confidence_weight": 0.10
                    }
                )
                db.merge(match)

            user.matched = True

        db.commit()
        rank_leads_task.delay(product_id)
```

### Tables Involved

- `discovered_users` (read)
- `user_ocean_scores` (read)
- `user_embeddings` (read)
- `motivation_categories` (read)
- `motivation_ocean_profiles` (read)
- `lead_matches` (write)

---

## 12. Module: Lead Ranking

### What to Build

A Celery task that aggregates `lead_matches`, picks the best motivation category per user, sorts by compatibility score, assigns ranks and tiers, and writes to the `leads` table.

### Why It Exists

A user may match multiple motivation categories. We collapse this to one lead record with their best match, rank all users for a product, and label them Hot / Warm / Cold for easy use in the dashboard.

### Inputs

- All `lead_matches` for a product

### Outputs

- N rows in `leads` (one per user per product)
- Ranks assigned 1..N
- Tiers: Hot (top 15%), Warm (next 35%), Cold (remaining 50%)

### Implementation

**`app/workers/tasks/matching_tasks.py` (continued)**
```python
@celery.task(name="tasks.rank_leads")
def rank_leads_task(product_id: str):
    with get_sync_session() as db:
        # Get best match per user
        best_matches = (
            db.execute(
                text("""
                    SELECT DISTINCT ON (user_id)
                        user_id,
                        motivation_category_id,
                        compatibility_score
                    FROM lead_matches
                    WHERE product_id = :product_id
                    ORDER BY user_id, compatibility_score DESC
                """),
                {"product_id": product_id}
            ).fetchall()
        )

        # Sort by compatibility score descending
        sorted_matches = sorted(best_matches, key=lambda x: x.compatibility_score, reverse=True)
        total = len(sorted_matches)

        hot_cutoff   = int(total * 0.15)
        warm_cutoff  = int(total * 0.50)

        for rank, match in enumerate(sorted_matches, start=1):
            if rank <= hot_cutoff:
                tier = "hot"
            elif rank <= warm_cutoff:
                tier = "warm"
            else:
                tier = "cold"

            lead = Lead(
                product_id=product_id,
                user_id=match.user_id,
                best_motivation_category_id=match.motivation_category_id,
                rank=rank,
                compatibility_score=match.compatibility_score,
                tier=tier,
                status="new"
            )
            db.merge(lead)

        product = db.query(Product).get(product_id)
        product.status = "completed"
        product.pipeline_step = 10
        db.commit()
```

### Tables Involved

- `lead_matches` (read)
- `leads` (write)
- `products` (status update)

---

## 13. Module: Dashboard

### What to Build

A read-heavy layer of APIs and frontend pages that display ranked leads, personality insights, motivation category breakdowns, pipeline status, and product analytics.

### Why It Exists

The dashboard is the product — it's what companies pay for. Everything else feeds into it. It must be fast, scannable, and actionable.

### Pages

#### Dashboard Home (`/dashboard`)

Displays:
- Total products, total leads discovered, pipeline health
- Recent activity feed (job started, leads ranked, etc.)
- Top 10 leads across all products

#### Product Detail (`/dashboard/products/{id}`)

Displays:
- Pipeline tracker: 10-step visual progress bar
- Status: pending → analyzing → motivations_generated → discovering → ...
- Quick stats: users discovered, users scored, leads count

#### Motivations (`/dashboard/products/{id}/motivations`)

For each motivation category:
- Name + description
- OCEAN radar chart (5-axis polygon)
- Interest tags as chips
- Search keywords

#### Discovery (`/dashboard/products/{id}/discovery`)

- Job status bar
- Live user count (polls every 5 seconds)
- Table of discovered users with bio, platform, location

#### Leads (`/dashboard/products/{id}/leads`)

Primary view. Features:
- Sortable table: rank, username, score, tier, motivation match, status
- Filter by tier, status, min score
- Click to open Lead Drawer (slide panel)

**Lead Drawer contains:**
- Platform profile link
- Bio
- OCEAN scores (bar chart + radar)
- Matched motivation category
- Score breakdown (personality / interest / activity / confidence)
- Status dropdown (new → viewed → contacted)
- LLM reasoning text

### Frontend Implementation

**`src/components/leads/LeadsTable.tsx`**
```tsx
"use client";
import { useLeads } from "@/lib/hooks/useLeads";
import { LeadDrawer } from "./LeadDrawer";
import { TierBadge } from "./TierBadge";
import { useState } from "react";

export function LeadsTable({ productId }: { productId: string }) {
  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null);
  const [filters, setFilters] = useState({ tier: "", minScore: 0 });

  const { data, isLoading } = useLeads(productId, filters);

  if (isLoading) return <LeadsTableSkeleton />;

  return (
    <>
      <div className="rounded-lg border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50">
              <th className="p-3 text-left">Rank</th>
              <th className="p-3 text-left">User</th>
              <th className="p-3 text-left">Motivation Match</th>
              <th className="p-3 text-left">Score</th>
              <th className="p-3 text-left">Tier</th>
              <th className="p-3 text-left">Status</th>
            </tr>
          </thead>
          <tbody>
            {data?.leads.map((lead) => (
              <tr
                key={lead.id}
                className="border-b hover:bg-muted/30 cursor-pointer"
                onClick={() => setSelectedLeadId(lead.id)}
              >
                <td className="p-3 font-mono text-muted-foreground">#{lead.rank}</td>
                <td className="p-3">
                  <div className="font-medium">{lead.user.username}</div>
                  <div className="text-xs text-muted-foreground">{lead.user.platform}</div>
                </td>
                <td className="p-3 text-sm">{lead.best_motivation}</td>
                <td className="p-3">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-16 rounded bg-muted overflow-hidden">
                      <div
                        className="h-full bg-primary"
                        style={{ width: `${lead.compatibility_score * 100}%` }}
                      />
                    </div>
                    <span className="font-mono text-xs">
                      {(lead.compatibility_score * 100).toFixed(0)}%
                    </span>
                  </div>
                </td>
                <td className="p-3"><TierBadge tier={lead.tier} /></td>
                <td className="p-3">{lead.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selectedLeadId && (
        <LeadDrawer
          leadId={selectedLeadId}
          onClose={() => setSelectedLeadId(null)}
        />
      )}
    </>
  );
}
```

**`src/components/motivations/OceanRadarChart.tsx`**
```tsx
"use client";
import {
  Radar, RadarChart, PolarGrid,
  PolarAngleAxis, ResponsiveContainer
} from "recharts";

interface OceanProfile {
  openness: number;
  conscientiousness: number;
  extraversion: number;
  agreeableness: number;
  emotional_stability: number;
}

export function OceanRadarChart({ profile, label }: { profile: OceanProfile; label?: string }) {
  const data = [
    { dimension: "Openness",          value: profile.openness },
    { dimension: "Conscientiousness", value: profile.conscientiousness },
    { dimension: "Extraversion",      value: profile.extraversion },
    { dimension: "Agreeableness",     value: profile.agreeableness },
    { dimension: "Stability",         value: profile.emotional_stability }
  ];

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data}>
          <PolarGrid />
          <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 12 }} />
          <Radar
            name={label}
            dataKey="value"
            stroke="#6366f1"
            fill="#6366f1"
            fillOpacity={0.25}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
```

**`src/components/products/PipelineTracker.tsx`**
```tsx
const PIPELINE_STEPS = [
  { step: 1, label: "Product Submitted" },
  { step: 2, label: "Motivations Generated" },
  { step: 3, label: "Discovery Started" },
  { step: 4, label: "Content Collected" },
  { step: 5, label: "NLP Processing" },
  { step: 6, label: "OCEAN Scoring" },
  { step: 7, label: "Matching Engine" },
  { step: 8, label: "Lead Ranking" },
  { step: 9, label: "Leads Ready" },
];

export function PipelineTracker({ currentStep }: { currentStep: number }) {
  return (
    <div className="flex items-center gap-1">
      {PIPELINE_STEPS.map((s, i) => (
        <div key={s.step} className="flex items-center gap-1">
          <div className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold
            ${s.step < currentStep ? "bg-primary text-white" :
              s.step === currentStep ? "bg-primary/20 border-2 border-primary text-primary" :
              "bg-muted text-muted-foreground"}`}>
            {s.step < currentStep ? "✓" : s.step}
          </div>
          {i < PIPELINE_STEPS.length - 1 && (
            <div className={`h-0.5 w-8 ${s.step < currentStep ? "bg-primary" : "bg-muted"}`} />
          )}
        </div>
      ))}
    </div>
  );
}
```

### Tables Involved

- `leads` (read)
- `discovered_users` (read)
- `user_ocean_scores` (read)
- `lead_matches` (read)
- `motivation_categories` (read)
- `products` (read)

---

## 14. Week-by-Week Roadmap

### Phase 1: Foundation (Weeks 1-2)

**Week 1**
- [ ] Git monorepo setup (backend/, frontend/, docker-compose.yml)
- [ ] PostgreSQL + pgvector setup on Docker
- [ ] FastAPI project skeleton: main.py, config.py, database.py
- [ ] SQLAlchemy models for all 12 tables
- [ ] Alembic migrations (all tables + indexes)
- [ ] CRUD endpoints: companies, products
- [ ] Test: create company, create product via Postman

**Week 2**
- [ ] Next.js 14 setup with Tailwind + shadcn/ui
- [ ] Layout: sidebar, header
- [ ] Landing page
- [ ] Register / login page (simple API key flow)
- [ ] Product submission form (multi-step)
- [ ] Product list page
- [ ] API client (axios instance) and React Query setup

**Deliverable:** Company can register, submit a product, see it in the list.

---

### Phase 2: Motivation Generation (Weeks 3-4)

**Week 3**
- [ ] Ollama setup on Oracle Free Tier VM
- [ ] Pull Llama 3.1:8b on Oracle VM
- [ ] `app/ml/llm_client.py` — Ollama HTTP client
- [ ] `app/ml/motivation_prompter.py` — prompt builder + parser
- [ ] Celery + Redis setup (docker-compose)
- [ ] `tasks.generate_motivations` Celery task
- [ ] Wire: product creation → auto-trigger motivation generation

**Week 4**
- [ ] Motivations API endpoints
- [ ] Frontend: motivation categories page
- [ ] OceanRadarChart component (Recharts)
- [ ] MotivationCard component
- [ ] Test: submit product → wait → see 5 motivation categories with OCEAN profiles

**Deliverable:** Product analysis + motivation generation is fully automated.

---

### Phase 3: User Discovery (Weeks 5-6)

**Week 5**
- [ ] Reddit API setup (PRAW) — register app at reddit.com/prefs/apps
- [ ] `app/ml/discovery/reddit_discoverer.py`
- [ ] `map_keywords_to_subreddits` utility function
- [ ] Mock discoverer for offline testing
- [ ] `tasks.run_discovery` Celery task
- [ ] Discovery job API endpoints

**Week 6**
- [ ] Content collection: fetch user's posts from Reddit API
- [ ] `tasks.collect_content` Celery task
- [ ] Store content in `user_content`
- [ ] Frontend: discovery page with job status + live user count
- [ ] Test: start discovery → see users appearing in real time

**Deliverable:** Platform can discover 200-300 real Reddit users for a product category.

---

### Phase 4: NLP Pipeline (Weeks 7-8)

**Week 7**
- [ ] Install and configure: sentence-transformers, empath, bertopic, spacy
- [ ] Download spaCy model: `python -m spacy download en_core_web_sm`
- [ ] `app/ml/embeddings.py` (singleton pattern)
- [ ] `app/ml/empath_analyzer.py`
- [ ] `app/ml/bertopic_modeler.py`
- [ ] `app/ml/spacy_processor.py`
- [ ] `app/utils/text_cleaner.py`

**Week 8**
- [ ] `app/services/nlp_service.py` — full pipeline
- [ ] `tasks.process_nlp_batch` — batched Celery task
- [ ] Wire: content collected → auto-trigger NLP batch
- [ ] Unit tests: test each NLP module independently
- [ ] Test: process 10 users end-to-end, inspect stored features

**Deliverable:** NLP features (embeddings, Empath, topics) stored for all collected users.

---

### Phase 5: OCEAN Scoring (Weeks 9-10)

**Week 9**
- [ ] `app/ml/ocean_prompter.py` — prompt builder + JSON parser
- [ ] `tasks.score_ocean_batch` — batched Celery task with auto-requeue
- [ ] Wire: NLP done → auto-trigger OCEAN batch
- [ ] Handle Ollama timeout/retry logic
- [ ] Test: score 20 real users, review outputs

**Week 10**
- [ ] Confidence score calibration
- [ ] Rate limiting for Ollama (avoid overloading 8B model)
- [ ] Frontend: user profile page with OCEAN scores
- [ ] Test: end-to-end pipeline from product submission to OCEAN scores

**Deliverable:** All discovered users have OCEAN scores with confidence ratings.

---

### Phase 6: Matching + Ranking (Weeks 11-12)

**Week 11**
- [ ] `app/services/matching_service.py` — all 4 score functions
- [ ] `tasks.run_matching` — N×M matching computation
- [ ] pgvector cosine similarity for interest matching (optional optimization)
- [ ] Wire: OCEAN done → auto-trigger matching

**Week 12**
- [ ] `tasks.rank_leads` — ranking + tiering
- [ ] Leads API endpoints (list, detail, status update, export)
- [ ] Frontend: leads table with sorting + filtering
- [ ] Lead drawer component
- [ ] Test: complete pipeline on 100 users, verify ranking makes intuitive sense

**Deliverable:** Ranked, tiered leads available in dashboard.

---

### Phase 7: Dashboard + Polish (Weeks 13-14)

**Week 13**
- [ ] Dashboard home page (stats cards, activity feed, top leads)
- [ ] Analytics page (tier distribution chart, score histogram)
- [ ] Pipeline tracker component
- [ ] CSV export endpoint + frontend button
- [ ] Lead status management (viewed/contacted/converted)

**Week 14**
- [ ] Mobile-responsive layout
- [ ] Error states and empty states for all pages
- [ ] Loading skeletons
- [ ] Toast notifications for pipeline events
- [ ] Pagination on leads table

**Deliverable:** Full dashboard ready for demo.

---

### Phase 8: Testing + Deployment (Weeks 15-16)

**Week 15**
- [ ] Integration test: full pipeline with mock data (fixture users)
- [ ] Unit tests: matching engine, prompt parsers, text cleaner
- [ ] API endpoint tests (pytest + httpx)
- [ ] Dockerfiles for backend + frontend
- [ ] docker-compose.yml for local full-stack run

**Week 16**
- [ ] Railway deployment: FastAPI + Celery + Redis + PostgreSQL
- [ ] Vercel deployment: Next.js
- [ ] Oracle VM: Ollama service setup, firewall rules, Nginx reverse proxy
- [ ] Environment variables in Railway + Vercel dashboards
- [ ] Grafana Cloud: connect to Railway PostgreSQL, build basic dashboard
- [ ] Smoke test on production environment

**Deliverable:** Platform deployed and accessible. End-to-end demo working.

---

## 15. Development Order

Build in this strict order. Each step enables the next.

```
1. PostgreSQL schema + migrations
2. FastAPI skeleton + company/product CRUD
3. Next.js + product submission UI
4. Ollama + motivation generation (Celery)
5. Motivation category UI
6. Reddit discovery (Celery)
7. Content collection (Celery)
8. Discovery UI (live polling)
9. NLP pipeline (Celery batch)
10. OCEAN scoring (Celery batch)
11. Matching engine (Celery)
12. Lead ranking (Celery)
13. Leads dashboard
14. Analytics + export
15. Tests
16. Deployment
```

---

## 16. MVP Scope

The MVP is everything needed for one company to submit one product and receive a ranked lead list.

### In MVP

- [ ] Company registration (API key based, no OAuth)
- [ ] Product submission form
- [ ] Automatic motivation category generation (Llama 3.1)
- [ ] Reddit-based user discovery
- [ ] Content collection from Reddit posts
- [ ] Full NLP pipeline (all 4 tools)
- [ ] OCEAN scoring via Ollama
- [ ] Matching engine (all 4 score components)
- [ ] Lead ranking with Hot/Warm/Cold tiers
- [ ] Dashboard with lead table + lead drawer
- [ ] CSV export

### Not In MVP (Post-MVP)

- Twitter/X API integration
- Instagram integration
- Company authentication (OAuth, JWT)
- Multi-user team support
- Email notifications when pipeline completes
- Webhook integrations (Salesforce, HubSpot)
- A/B testing motivation categories
- Grafana dashboard (use Railway built-in metrics for now)
- GDPR/privacy consent flows
- Payment integration

---

## 17. Deployment Plan

### Architecture

```
Internet
   │
   ├── Vercel (Next.js frontend)
   │     └── calls Railway API
   │
   ├── Railway (FastAPI + Celery workers)
   │     ├── FastAPI service (web server)
   │     ├── Celery worker service (background tasks)
   │     ├── Redis service (Celery broker)
   │     └── PostgreSQL service (with pgvector)
   │
   └── Oracle Free Tier VM (Ubuntu 22.04)
         └── Ollama serving Llama 3.1:8b on port 11434
               (accessible by Railway via private IP or public IP + firewall rule)
```

### Railway Setup

**Services:**
1. `api` — FastAPI web server
2. `worker` — Celery worker (same codebase, different start command)
3. `redis` — Redis 7 (Railway template)
4. `postgres` — PostgreSQL 16 (Railway template, enable pgvector via init SQL)

**Environment Variables (Railway):**
```
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
OLLAMA_BASE_URL=http://<oracle-vm-ip>:11434
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
SECRET_KEY=<random 64 char string>
ENVIRONMENT=production
```

**Dockerfiles:**

`backend/Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m spacy download en_core_web_sm
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`backend/Dockerfile.worker` (or use Railway start command override):
```dockerfile
CMD ["celery", "-A", "app.workers.celery_app", "worker",
     "--loglevel=info", "--concurrency=2", "-Q", "default"]
```

### Vercel Setup

```
Framework: Next.js
Root directory: frontend/
Environment Variables:
  NEXT_PUBLIC_API_URL=https://<railway-api-url>
```

### Oracle Free Tier VM Setup

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull Llama 3.1 8B
ollama pull llama3.1:8b

# Create systemd service for Ollama
sudo systemctl enable ollama
sudo systemctl start ollama

# Open port 11434 in Oracle firewall (Security List)
# Add ingress rule: TCP, port 11434, source: Railway IP range

# Optional: Nginx reverse proxy for HTTPS
sudo apt install nginx
```

### pgvector on Railway PostgreSQL

Run this after Railway PostgreSQL starts:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```
Set this in Railway as a one-time init script or run via migration.

### Grafana (Post-MVP)

Connect Grafana Cloud free tier to Railway PostgreSQL:
- Dashboard 1: Pipeline health (jobs running, failed, completed)
- Dashboard 2: Lead quality distribution (score histogram per product)
- Dashboard 3: OCEAN score distributions across user base

---

## 18. Testing Strategy

### Unit Tests

Test all pure functions with no database or network dependencies.

**Priority targets:**
- `calculate_personality_match` — test edge cases (identical, maximum difference)
- `calculate_interest_match` — test with known embeddings
- `calculate_compatibility` — test weight math
- `parse_ocean_response` — test malformed JSON, missing keys, out-of-range values
- `build_ocean_prompt` — test with missing bio, empty posts
- `clean_text` — test URL removal, emoji handling, encoding issues

```python
# tests/unit/test_matching_engine.py
def test_personality_match_identical():
    ocean = {"openness": 7, "conscientiousness": 6, "extraversion": 5,
             "agreeableness": 6, "emotional_stability": 7}
    assert calculate_personality_match(ocean, ocean) == 1.0

def test_personality_match_maximum_distance():
    user   = {"openness": 0, "conscientiousness": 0, "extraversion": 0,
              "agreeableness": 0, "emotional_stability": 0}
    target = {"openness": 10, "conscientiousness": 10, "extraversion": 10,
              "agreeableness": 10, "emotional_stability": 10}
    assert calculate_personality_match(user, target) == 0.0

def test_ocean_parser_valid():
    raw = '{"openness": 7.5, "conscientiousness": 6.0, "extraversion": 7.0, ' \
          '"agreeableness": 6.5, "emotional_stability": 6.0, "confidence": 0.75, ' \
          '"reasoning": "Active poster"}'
    result = parse_ocean_response(raw)
    assert result["openness"] == 7.5
    assert result["confidence"] == 0.75

def test_ocean_parser_clamping():
    raw = '{"openness": 12, "conscientiousness": -1, "extraversion": 5, ' \
          '"agreeableness": 5, "emotional_stability": 5, "confidence": 1.5, "reasoning": ""}'
    result = parse_ocean_response(raw)
    assert result["openness"] == 10.0
    assert result["conscientiousness"] == 0.0
    assert result["confidence"] == 1.0
```

### Integration Tests

Test database interactions and service-level flows using a test database.

**Priority targets:**
- Product creation → motivation generation task fires
- NLP service processes user content end-to-end
- Matching engine stores correct number of `lead_matches` rows
- Lead ranking assigns consecutive ranks starting from 1

```python
# tests/integration/test_product_pipeline.py
@pytest.mark.asyncio
async def test_create_product_triggers_motivation_task(
    async_client, test_db, mock_celery
):
    company = await create_test_company(test_db)
    response = await async_client.post(
        "/api/v1/products",
        json={"name": "Premium Sofa", "category": "Furniture",
              "price_range": "premium", "target_location": "Chennai",
              "description": "Italian leather 3-seater"},
        headers={"X-API-Key": company.api_key}
    )
    assert response.status_code == 201
    mock_celery.tasks["tasks.generate_motivations"].assert_called_once()
```

### API Tests

Test all endpoints for correct status codes, schema compliance, and error handling.

```python
# tests/integration/test_api_endpoints.py
def test_get_leads_requires_api_key(client):
    response = client.get("/api/v1/products/fake-id/leads")
    assert response.status_code == 401

def test_get_leads_returns_paginated(client, seeded_leads):
    response = client.get(
        f"/api/v1/products/{seeded_leads.product_id}/leads?limit=5",
        headers={"X-API-Key": seeded_leads.api_key}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["leads"]) <= 5
    assert "total" in data
```

### End-to-End Tests

Use the mock discoverer fixture (500 fake users in JSON) to run the full pipeline in CI.

```
pytest tests/e2e/test_full_pipeline.py -v
```

This test:
1. Creates company + product
2. Waits for motivation generation (mock Ollama)
3. Runs mock discovery (500 fixture users)
4. Runs NLP on all users
5. Runs mock OCEAN scoring (fixture responses)
6. Runs matching
7. Asserts leads table has correct count + rank sequence

### CI Setup (GitHub Actions)

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_PASSWORD: test
        ports: ["5432:5432"]
      redis:
        image: redis:7
        ports: ["6379:6379"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r backend/requirements.txt
      - run: python -m spacy download en_core_web_sm
      - run: pytest backend/tests/ -v --tb=short
        env:
          DATABASE_URL: postgresql+asyncpg://postgres:test@localhost:5432/test
          REDIS_URL: redis://localhost:6379
          OLLAMA_BASE_URL: http://mock  # mocked in tests
```

---

## Environment Variables Reference

```env
# backend/.env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/psycholead
REDIS_URL=redis://localhost:6379/0
OLLAMA_BASE_URL=http://localhost:11434
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
SECRET_KEY=change_me_in_production_use_64_random_chars
ENVIRONMENT=development
CELERY_CONCURRENCY=2
MAX_USERS_PER_DISCOVERY=500
OCEAN_BATCH_SIZE=10

# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## requirements.txt

```
fastapi==0.110.0
uvicorn[standard]==0.27.0
sqlalchemy[asyncio]==2.0.28
asyncpg==0.29.0
alembic==1.13.1
pydantic==2.6.1
pydantic-settings==2.2.0
celery[redis]==5.3.6
redis==5.0.1
httpx==0.27.0
sentence-transformers==2.7.0
empath==0.89
bertopic==0.16.2
spacy==3.7.4
praw==7.7.1
pgvector==0.2.5
numpy==1.26.4
scikit-learn==1.4.0
pytest==8.0.2
pytest-asyncio==0.23.5
pytest-mock==3.12.0
```

---

## package.json (key dependencies)

```json
{
  "dependencies": {
    "next": "14.1.0",
    "react": "^18",
    "react-dom": "^18",
    "@tanstack/react-query": "^5",
    "zustand": "^4",
    "axios": "^1.6",
    "recharts": "^2.12",
    "lucide-react": "^0.344",
    "tailwindcss": "^3.4",
    "class-variance-authority": "^0.7",
    "clsx": "^2.1",
    "tailwind-merge": "^2.2"
  }
}
```

---

*Document version: 1.0 — Generated 2026-06-01*
*Status: Developer-ready. Build begins from Section 14, Week 1.*
