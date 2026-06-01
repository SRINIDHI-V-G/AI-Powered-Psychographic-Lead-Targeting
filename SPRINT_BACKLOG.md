# Sprint Backlog — AI Psychographic Lead Intelligence Platform
## 8 Sprints × 2 Weeks = 16-Week MVP

---

## How to Read This Document

**Story Point Scale (Fibonacci):**
| Points | Meaning |
|---|---|
| 1 | < 2 hours. Config, boilerplate, 1-file change. |
| 2 | Half a day. One clear function or component. |
| 3 | Full day. One service/module with tests. |
| 5 | 2-3 days. Complex module touching 3+ files. |
| 8 | Full week. End-to-end integration across layers. |
| 13 | > 1 week. Should be broken down further. |

**Role Codes:**
- `BE` — Backend Engineer (FastAPI, Celery, DB)
- `ML` — ML/AI Engineer (NLP, Ollama, embeddings)
- `FE` — Frontend Engineer (Next.js, Tailwind, React)
- `FS` — Full Stack / Tech Lead (can swing any layer)

**Task ID format:** `S{sprint}-{role}-{number}`

**Done means:**
- Code written and committed
- Locally tested (manual or automated)
- No console errors, no uncaught exceptions
- Reviewed by at least one other person (or self-reviewed for solo teams)

---

## Dependency Map (Read Before Doing Anything)

```
Sprint 1: DB Schema + Project Skeleton
    ↓
Sprint 2: Company/Product CRUD + Product Submission UI
    ↓
Sprint 3: Motivation Generation (Llama) + Motivation UI
    ↓
Sprint 4: Reddit Discovery + Content Collection + Discovery UI
    ↓
Sprint 5: NLP Pipeline (Embeddings + Empath + BERTopic + spaCy)
    ↓
Sprint 6: OCEAN Scoring (Llama Batch)
    ↓
Sprint 7: Matching Engine + Lead Ranking
    ↓
Sprint 8: Dashboard Polish + Testing + Deployment
```

No sprint can begin until the one above it is **fully done**. ML work in Sprint 3 and Sprint 6 is the most likely to cause delays — start Ollama setup on Day 1 of the project, not Day 1 of Sprint 3.

---

## SPRINT 1
### Theme: Foundation — Database, Project Structure, DevOps
### Duration: Weeks 1–2
### Sprint Goal: A developer on the team can clone the repo, run `docker-compose up`, hit `GET /health`, and see the database with all 12 tables created.

---

### What You Are Building

The entire project skeleton. No business logic exists yet. This sprint is infrastructure-only. When this sprint ends, the foundation for every other sprint is in place.

---

### User Stories

**STORY S1-1: Local dev environment boots in one command**
> As a developer, I can clone the repo, run one command, and have the full stack running locally.

Acceptance Criteria:
- `docker-compose up` starts: FastAPI, PostgreSQL (with pgvector), Redis, Celery worker
- `GET http://localhost:8000/health` returns `{"status": "ok", "db": "connected", "redis": "connected"}`
- All 12 database tables exist with correct columns and indexes
- `.env.example` file is present with all required variable names

---

**STORY S1-2: Database schema is complete and version-controlled**
> As a team, we have a single source of truth for the database structure that can be reproduced from scratch.

Acceptance Criteria:
- Alembic migration `001_initial_schema.py` creates all 12 tables
- Alembic migration `002_add_pgvector.py` enables vector extension and adds vector columns
- Alembic migration `003_add_indexes.py` adds all indexes (including ivfflat vector indexes)
- `alembic upgrade head` runs cleanly on a fresh PostgreSQL instance
- `alembic downgrade base` drops everything cleanly

---

**STORY S1-3: Backend project structure follows the agreed layout**
> As a backend developer, I can find any file in an expected location without asking.

Acceptance Criteria:
- All folders from the implementation plan exist: `app/models/`, `app/schemas/`, `app/routers/`, `app/services/`, `app/ml/`, `app/workers/`, `app/utils/`
- `app/config.py` loads settings from `.env` via Pydantic `BaseSettings`
- `app/database.py` has async SQLAlchemy engine + session factory
- `app/main.py` mounts all routers, has CORS middleware, has `/health` endpoint
- `requirements.txt` is pinned and installs cleanly

---

**STORY S1-4: Frontend project structure is set up**
> As a frontend developer, I can start building components without setup work.

Acceptance Criteria:
- Next.js 14 with App Router initialized
- Tailwind CSS configured and working
- shadcn/ui initialized with at least: `button`, `card`, `input`, `badge`, `table`, `dialog`, `sheet`
- Axios instance in `src/lib/api.ts` pointing to `NEXT_PUBLIC_API_URL`
- React Query provider in root layout
- Zustand store file created (empty store)
- `npm run dev` boots without errors

---

### Technical Tasks

| ID | Task | Role | Points | Notes |
|---|---|---|---|---|
| S1-BE-1 | Create monorepo: `backend/`, `frontend/`, `docker-compose.yml` | FS | 1 | Git init, `.gitignore`, `README.md` |
| S1-BE-2 | Write `docker-compose.yml` with: FastAPI, PostgreSQL 16 (pgvector image), Redis 7, Celery worker | BE | 3 | Use `pgvector/pgvector:pg16` image. Mount code as volume for hot reload. |
| S1-BE-3 | FastAPI skeleton: `main.py`, `config.py`, `database.py` | BE | 2 | Async SQLAlchemy engine. `DATABASE_URL` from env. |
| S1-BE-4 | Write ALL SQLAlchemy models (12 tables) | BE | 5 | One file per model group as per folder structure. Include all columns, types, relationships, FKs. |
| S1-BE-5 | Alembic setup + migration 001: initial schema (10 tables, no vectors) | BE | 3 | `alembic init migrations`. Auto-generate from models, then hand-edit for correctness. |
| S1-BE-6 | Alembic migration 002: enable pgvector, add VECTOR columns to `motivation_categories` and `user_embeddings` | BE | 2 | Must run `CREATE EXTENSION vector` before column creation. |
| S1-BE-7 | Alembic migration 003: all indexes including two ivfflat vector indexes | BE | 2 | ivfflat requires data to exist before index creation in production — add note in migration. |
| S1-BE-8 | `GET /health` endpoint that pings DB and Redis | BE | 1 | Return 503 if either is down. |
| S1-BE-9 | Celery app setup: `app/workers/celery_app.py` with Redis broker | BE | 2 | Worker boots via `celery -A app.workers.celery_app worker`. Verify with `celery inspect ping`. |
| S1-BE-10 | `app/utils/text_cleaner.py`: `clean_text()` function | BE | 2 | Strip URLs, HTML tags, normalize whitespace, handle None input. Write 5 unit tests. |
| S1-BE-11 | `requirements.txt` with all pinned dependencies | BE | 1 | All packages from implementation plan. Test: `pip install -r requirements.txt` succeeds in clean venv. |
| S1-FE-1 | Next.js 14 project init with TypeScript + Tailwind | FE | 1 | `npx create-next-app@latest frontend --typescript --tailwind --app` |
| S1-FE-2 | shadcn/ui init + install 8 base components | FE | 1 | `npx shadcn-ui@latest init`. Add: button, card, input, badge, table, dialog, sheet, skeleton |
| S1-FE-3 | `src/lib/api.ts`: axios instance with base URL, error interceptor, API key header | FE | 2 | Read `NEXT_PUBLIC_API_URL` from env. Interceptor logs 4xx/5xx errors. |
| S1-FE-4 | React Query provider in `src/app/layout.tsx` | FE | 1 | `QueryClientProvider` wrapping children. |
| S1-FE-5 | Zustand store: `src/store/useAppStore.ts` | FE | 1 | Empty store with `selectedProductId` field. |
| S1-FE-6 | TypeScript type definitions: `product.ts`, `motivation.ts`, `user.ts`, `lead.ts` | FE | 2 | Match all API response shapes from implementation plan exactly. |
| S1-FE-7 | `.env.local.example` for frontend | FE | 1 | `NEXT_PUBLIC_API_URL=http://localhost:8000` |

**Sprint 1 Total: 36 points**

---

### Definition of Done for Sprint 1

```bash
# Verification commands — all must pass before Sprint 2 begins

docker-compose up -d
curl http://localhost:8000/health
# Expected: {"status":"ok","db":"connected","redis":"connected"}

cd backend && alembic upgrade head
# Expected: 12 tables visible in psql

cd backend && python -m pytest tests/unit/test_text_cleaner.py -v
# Expected: 5 tests pass

cd frontend && npm run build
# Expected: Build succeeds with 0 errors
```

---

### Risks and Blockers

- **pgvector on Railway:** The `pgvector/pgvector:pg16` Docker image works locally. Railway PostgreSQL requires a different activation (SQL command). Document this now, solve it in Sprint 8.
- **ivfflat indexes:** These fail on empty tables in some pgvector versions. Migration 003 should wrap the index creation in a `DO $$ IF EXISTS` guard or defer to after first data load.

---

### What NOT to Build in Sprint 1

- No UI pages beyond the blank Next.js default
- No business logic in any service
- No Ollama setup (do this in Sprint 3 prep)
- No Reddit API registration (do this in Sprint 4 prep)

---
---

## SPRINT 2
### Theme: Company + Product APIs + Product Submission UI
### Duration: Weeks 3–4
### Sprint Goal: A company can register, get an API key, submit a product, and see it listed in the dashboard with a "pending" status badge.

---

### What You Are Building

The front door of the platform. Company registration, API key issuance, product submission form, product list page, and the pipeline status display. No pipeline logic runs yet — the product just sits at `status: pending`.

---

### User Stories

**STORY S2-1: Company can register and receive an API key**
> As a company, I can submit my name and email and receive an API key I can use for all future requests.

Acceptance Criteria:
- `POST /api/v1/companies` accepts `{name, email, industry, website}` and returns `{id, api_key, created_at}`
- API key is a 64-character random hex string generated at registration
- Duplicate email returns `409 Conflict` with clear message
- API key is stored hashed in the `companies` table (return plaintext once only)
- `GET /api/v1/companies/me` with valid `X-API-Key` header returns company profile

---

**STORY S2-2: Company can submit a product**
> As a company, I can fill out a form describing my product and submit it to start the pipeline.

Acceptance Criteria:
- `POST /api/v1/products` creates product with status `pending`
- Required fields: `name`, `description`, `category`, `price_range`, `target_location`
- Optional fields: `subcategory`, `keywords`
- Returns `{id, name, status, pipeline_step, created_at}`
- `GET /api/v1/products` returns all products for the authenticated company
- `GET /api/v1/products/{id}` returns product detail with `status` and `pipeline_step`
- `GET /api/v1/products/{id}/status` is a lightweight poll endpoint returning only `{id, status, pipeline_step, updated_at}`

---

**STORY S2-3: Frontend shows a working product submission form**
> As a company user, I can fill out the product form in the browser and see my product appear in the list.

Acceptance Criteria:
- Multi-step form with 3 steps: (1) Product details, (2) Location + pricing, (3) Keywords + review
- Validation: all required fields show inline error on submit
- On success: redirect to product detail page at `/dashboard/products/{id}`
- Product list at `/dashboard/products` shows all submitted products as cards
- Each product card shows: name, category, price range, status badge, created date
- Status badge colors: `pending` = grey, `analyzing` = blue (for future states)

---

**STORY S2-4: API authentication middleware works globally**
> As a developer, every protected endpoint rejects requests without a valid API key.

Acceptance Criteria:
- FastAPI dependency `get_current_company` extracts and validates `X-API-Key` header
- Invalid key returns `401 Unauthorized`
- Missing key returns `401 Unauthorized`
- All product endpoints use this dependency
- Health endpoint is public (no key required)

---

### Technical Tasks

| ID | Task | Role | Points | Notes |
|---|---|---|---|---|
| S2-BE-1 | `app/models/company.py`: add `api_key_hash` field | BE | 1 | Store SHA-256 hash. Return raw key once on creation. |
| S2-BE-2 | `app/services/company_service.py`: `create_company()`, `get_by_api_key()` | BE | 3 | Generate 64-char hex key, hash for storage. |
| S2-BE-3 | `app/routers/companies.py`: `POST /companies`, `GET /companies/me` | BE | 2 | Wire to company service. |
| S2-BE-4 | FastAPI auth dependency: `app/dependencies.py` → `get_current_company()` | BE | 2 | Header extraction, hash lookup, 401 on failure. |
| S2-BE-5 | `app/schemas/company.py`: `CompanyCreate`, `CompanyResponse`, `CompanyPublic` | BE | 1 | Pydantic v2 models. `api_key` only in `CompanyResponse` (returned once). |
| S2-BE-6 | `app/services/product_service.py`: `create_product()`, `get_products()`, `get_product()` | BE | 3 | No pipeline trigger yet — just DB CRUD. |
| S2-BE-7 | `app/routers/products.py`: `POST /products`, `GET /products`, `GET /products/{id}`, `GET /products/{id}/status` | BE | 2 | All routes require auth dependency. |
| S2-BE-8 | `app/schemas/product.py`: `ProductCreate`, `ProductResponse`, `ProductStatus` | BE | 2 | `ProductStatus` is lightweight: `{id, status, pipeline_step, updated_at}` only. |
| S2-BE-9 | Input validation: product description min 20 chars, location not blank | BE | 1 | Pydantic validators. |
| S2-BE-10 | Write integration tests for company + product endpoints | BE | 3 | Use `pytest` + `httpx.AsyncClient`. Test: create, get, duplicate email, bad API key. |
| S2-FE-1 | Dashboard layout: `src/app/dashboard/layout.tsx` with sidebar + header | FE | 3 | Sidebar: Dashboard, Products, Settings links. Header: company name. |
| S2-FE-2 | `src/components/layout/Sidebar.tsx` with navigation links | FE | 2 | Active link highlighting. Collapsed state on mobile. |
| S2-FE-3 | Product list page: `src/app/dashboard/products/page.tsx` | FE | 2 | Grid of ProductCards. Empty state: "Submit your first product" CTA. |
| S2-FE-4 | `src/components/products/ProductCard.tsx` | FE | 2 | Shows: name, category, price range tag, status badge, "View" button. |
| S2-FE-5 | `src/components/layout/PipelineStatusBadge.tsx` | FE | 1 | Maps status string to color + label. |
| S2-FE-6 | Product submission: `src/app/dashboard/products/new/page.tsx` | FE | 2 | Multi-step form shell with 3 steps, Back/Next buttons. |
| S2-FE-7 | `src/components/products/ProductForm.tsx`: all form fields, validation, submission | FE | 5 | Step 1: name, description, category, subcategory. Step 2: price_range (radio), location, country. Step 3: keywords (tag input), review summary. |
| S2-FE-8 | Product detail page: `src/app/dashboard/products/[id]/page.tsx` | FE | 3 | Shows product metadata + status + `pipeline_step`. Uses `GET /products/{id}/status` every 5s if status != completed/failed. |
| S2-FE-9 | `src/lib/hooks/useProducts.ts`: `useProducts()`, `useProduct(id)`, `useProductStatus(id)` | FE | 2 | React Query hooks. `useProductStatus` has `refetchInterval: 5000` when status is active. |
| S2-FE-10 | Company registration page: `src/app/(auth)/register/page.tsx` | FE | 2 | Form: name, email, industry, website. On success: show API key once with copy button + warning that it won't be shown again. |
| S2-FE-11 | API key storage in localStorage + Axios header injection | FE | 2 | Store key on register. Inject as `X-API-Key` on every request. Redirect to login if 401. |

**Sprint 2 Total: 45 points**

---

### Definition of Done for Sprint 2

```bash
# Manual test sequence — run through completely before marking Sprint 2 done

# 1. Register company
curl -X POST http://localhost:8000/api/v1/companies \
  -H "Content-Type: application/json" \
  -d '{"name":"Comfort Furniture","email":"demo@comfort.com","industry":"Furniture"}'
# Returns: {id, api_key, ...}  ← save this api_key

# 2. Submit product
curl -X POST http://localhost:8000/api/v1/products \
  -H "X-API-Key: <your-api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Premium Sofa",
    "description": "A handcrafted 3-seater sofa with Italian full-grain leather...",
    "category": "Furniture",
    "price_range": "premium",
    "target_location": "Chennai"
  }'
# Returns: {id, status: "pending", pipeline_step: 0, ...}

# 3. Verify in browser
# Open http://localhost:3000/register → register → see API key
# Navigate to /dashboard/products → see "Premium Sofa" card with "pending" badge
# Click card → see product detail page
```

---

### Risks and Blockers

- **API key security:** MVP stores hash (SHA-256). If team skips hashing and stores plaintext, flag it immediately — fix before Sprint 8 deployment.
- **Multi-step form complexity:** ProductForm is the highest-risk FE task (5 points). If it's taking longer than 3 days, simplify to a single-page form for now and add multi-step in Sprint 8 polish.

---

### What NOT to Build in Sprint 2

- No pipeline trigger (the product just sits at `pending`)
- No motivation category display
- No Celery tasks
- No authentication other than API key (no OAuth, no JWT, no sessions)
- No `DELETE /products` (add in Sprint 8)

---
---

## SPRINT 3
### Theme: Motivation Generation (Llama + Celery) + Motivation UI
### Duration: Weeks 5–6
### Sprint Goal: Submit a product, wait 60-90 seconds, and see 5 motivation categories with OCEAN radar charts in the dashboard — generated automatically by Llama 3.1.

---

### What You Are Building

The first AI module. This is the "wow" moment of the platform. A company submits a product and the system generates structured psychographic buyer personas automatically. The Celery pipeline begins here.

---

### Pre-Sprint Setup (Do Before Sprint 3 Day 1)

```bash
# On Oracle Free Tier VM — set up BEFORE sprint begins
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama3.1:8b
# Verify:
curl http://localhost:11434/api/generate \
  -d '{"model":"llama3.1:8b","prompt":"Say hello","stream":false}'
# Open firewall port 11434 in Oracle Security List
# Test from Railway/local: curl http://<oracle-ip>:11434/api/generate ...
```

---

### User Stories

**STORY S3-1: Product submission automatically triggers motivation generation**
> As a company, after I submit a product, the system automatically starts analyzing it and generating buyer motivation categories — I don't have to trigger anything manually.

Acceptance Criteria:
- `POST /api/v1/products` now fires a Celery task `tasks.generate_motivations` immediately after DB commit
- Product status changes: `pending` → `analyzing` (when task starts) → `motivations_generated` (when done) → `failed` (on error with message)
- Task retries up to 3 times on Ollama failure (60-second backoff)
- Pipeline step advances to `2` on success

---

**STORY S3-2: Motivation categories are stored and retrievable**
> As a company, I can see the 5 motivation categories the system generated for my product.

Acceptance Criteria:
- `GET /api/v1/products/{id}/motivations` returns all categories with OCEAN profiles
- Each category has: `name`, `description`, `ocean` (5 scores), `interest_tags`, `search_keywords`, `hashtags`
- Category embeddings are stored in `motivation_categories.embedding` (vector 384)
- OCEAN scores are stored in `motivation_ocean_profiles`
- If motivations don't exist yet, returns empty array (not 404)

---

**STORY S3-3: Frontend auto-updates product status and shows motivation categories**
> As a company user, I can watch my product's status update in real time and then see the generated motivation categories.

Acceptance Criteria:
- Product detail page polls status every 5 seconds while `status != completed/failed/motivations_generated`
- When status becomes `motivations_generated`, page shows "View Motivations" button that navigates to motivations page
- Motivations page shows one card per category
- Each card shows: category name, description, OCEAN radar chart, interest tags as chips, search keywords
- OCEAN radar chart is interactive (hover shows dimension name + score)

---

### Technical Tasks

| ID | Task | Role | Points | Notes |
|---|---|---|---|---|
| S3-ML-1 | `app/ml/llm_client.py`: `OllamaClient` with `generate()` method | ML | 3 | httpx POST to Ollama. Timeout 120s. Log request/response sizes. |
| S3-ML-2 | `app/ml/motivation_prompter.py`: `build_motivation_prompt()` | ML | 3 | Full prompt from implementation plan. Test with 3 different products manually via curl before wiring. |
| S3-ML-3 | `app/ml/motivation_prompter.py`: `parse_motivation_response()` | ML | 3 | JSON parser with validation. Handles: malformed JSON, missing keys, wrong OCEAN ranges. Returns None on parse failure (don't crash). |
| S3-ML-4 | `app/ml/embeddings.py`: `EmbeddingModel` singleton | ML | 2 | Loads `all-MiniLM-L6-v2`. `encode(text)` returns `np.ndarray`. `encode_batch(texts)` for lists. |
| S3-BE-1 | `app/workers/tasks/product_tasks.py`: `generate_motivations_task` | BE | 5 | Full implementation from plan: call LLM, parse, embed category text, store categories + ocean profiles. Retry on failure. Update product status at each step. |
| S3-BE-2 | Wire product creation to fire Celery task | BE | 1 | Add `.delay()` call at end of `product_service.create_product()`. |
| S3-BE-3 | `app/services/motivation_service.py`: `get_motivations(product_id)` | BE | 2 | Fetch categories + join ocean profiles. |
| S3-BE-4 | `app/routers/motivations.py`: `GET /products/{id}/motivations`, `POST /products/{id}/motivations/regenerate` | BE | 2 | Regenerate deletes existing categories + re-fires Celery task. |
| S3-BE-5 | `app/schemas/motivation.py`: `MotivationCategoryResponse`, `MotivationListResponse` | BE | 1 | Include nested `ocean_profile` and all array fields. |
| S3-BE-6 | Unit tests: `test_motivation_prompter.py` | ML | 3 | Test: valid JSON parse, malformed JSON returns None, OCEAN clamping, missing fields. Use fixture LLM responses (no real Ollama call). |
| S3-BE-7 | Unit tests: `test_embeddings.py` | ML | 2 | Test: output shape is (384,), L2 norm ≈ 1.0, same text gives same embedding. |
| S3-FE-1 | `src/components/products/PipelineTracker.tsx` | FE | 2 | Visual 9-step pipeline progress bar. Active step highlighted. Completed steps show checkmark. |
| S3-FE-2 | Add PipelineTracker to product detail page | FE | 1 | Replaces plain status badge on detail page. |
| S3-FE-3 | `src/app/dashboard/products/[id]/motivations/page.tsx` | FE | 2 | Grid of MotivationCards. Loading skeleton while fetching. |
| S3-FE-4 | `src/components/motivations/MotivationCard.tsx` | FE | 3 | Card with: category name (bold), description, OCEAN radar chart, interest tags (chip list), keywords (small grey chips). |
| S3-FE-5 | `src/components/motivations/OceanRadarChart.tsx` | FE | 3 | Recharts RadarChart. 5 axes. Fill color `#6366f1` at 25% opacity. Hover tooltip. Accepts `OceanProfile` prop. |
| S3-FE-6 | `src/lib/hooks/useMotivations.ts`: `useMotivations(productId)` | FE | 1 | React Query. No polling needed (motivations don't change after generation). |
| S3-FE-7 | Update product detail page: show "View Motivations →" link when status = `motivations_generated` | FE | 1 | Conditional render. |

**Sprint 3 Total: 39 points**

---

### Definition of Done for Sprint 3

```
Manual verification sequence:

1. Register company + submit "Premium Sofa" product
2. Watch status badge on product detail page change:
   pending → analyzing → motivations_generated
   (should take 30-90 seconds)
3. Click "View Motivations"
4. See 5 cards with distinct category names
   e.g., "Aesthetic / Interior Design Focus"
         "Luxury / Status Signaling"
         "Durability & Long-Term Value"
         "Comfort & Family Living"
         "Budget-Conscious Purchase"
5. Click each card — radar chart shows 5 different OCEAN shapes
6. Run: SELECT count(*) FROM motivation_categories;  → should be 5
7. Run: SELECT count(*) FROM motivation_ocean_profiles;  → should be 5
8. Run: SELECT embedding IS NOT NULL FROM motivation_categories LIMIT 5;
   → should be 5 × 't'
```

---

### Risks and Blockers

- **Ollama latency:** Llama 3.1 8B on Oracle VM may take 30-90 seconds for the motivation prompt. This is expected. Do not optimize yet. Show a loading indicator.
- **JSON parsing failures:** Llama sometimes returns extra text before/after JSON. The parser must use regex to extract the JSON block, not `json.loads()` directly on the full response.
- **Oracle VM network:** If the Oracle VM is unreachable from Railway (Sprint 8), use local Ollama for development. The `OLLAMA_BASE_URL` env var handles this transparently.

---

### What NOT to Build in Sprint 3

- No ability to edit individual motivation categories yet (Sprint 8 polish)
- No manual discovery trigger yet
- No content collection
- No NLP or OCEAN scoring

---
---

## SPRINT 4
### Theme: User Discovery + Content Collection + Discovery UI
### Duration: Weeks 7–8
### Sprint Goal: Click "Start Discovery" for a product, wait, and see a live count of discovered Reddit users growing in the dashboard.

---

### What You Are Building

The data acquisition layer. The platform discovers real public Reddit users whose interests match the product's motivation keywords. This sprint also builds the content collector that fetches those users' posts and stores them for NLP.

---

### Pre-Sprint Setup (Do Before Sprint 4 Day 1)

```
1. Register a Reddit app at https://www.reddit.com/prefs/apps
   - Type: "script"
   - Name: "PsychographicLeads"
   - redirect uri: http://localhost:8080
   - Save: client_id and client_secret

2. Add to .env:
   REDDIT_CLIENT_ID=your_client_id
   REDDIT_CLIENT_SECRET=your_client_secret

3. Test access:
   python -c "import praw; r = praw.Reddit(client_id='x', client_secret='y', user_agent='test'); print(list(r.subreddit('interiordesign').hot(limit=3)))"
```

---

### User Stories

**STORY S4-1: Company can start a discovery job for their product**
> As a company, I can trigger discovery for my product and have the system automatically search for relevant Reddit users.

Acceptance Criteria:
- `POST /api/v1/products/{id}/discovery/start` creates a `discovery_jobs` row and fires a Celery task
- Request body: `{sources, max_users, search_config}` — all optional with sensible defaults
- Returns job ID immediately (async — don't wait for discovery to finish)
- Discovery uses keywords from ALL motivation categories' `search_keywords` arrays (merged + deduplicated)
- Discovery uses interest tags to map to subreddits

---

**STORY S4-2: Discovery runs and finds real users**
> As a developer, the discovery task actually calls Reddit's API and stores found users.

Acceptance Criteria:
- `RedditDiscoverer` searches relevant subreddits using merged keywords
- `map_keywords_to_subreddits()` maps interest tags to a predefined list of subreddits
- Found users stored in `discovered_users` table
- Duplicate users (same `platform_user_id` + `discovery_job_id`) are skipped via `INSERT ... ON CONFLICT DO NOTHING`
- `discovery_jobs.users_discovered` is updated in real time
- After discovery: content collection task fires automatically

---

**STORY S4-3: Content is collected for each discovered user**
> As a system, after a user is discovered, their public posts are collected and stored.

Acceptance Criteria:
- For each discovered Reddit user, fetch up to 25 most recent posts/comments
- Store each as a `user_content` row with correct `content_type`
- User's bio/about stored as `content_type: 'bio'`
- After content collected: `discovered_users.content_collected = true`
- After all users in job have content collected: product status → `discovering`, pipeline_step → 3

---

**STORY S4-4: Dashboard shows discovery progress in real time**
> As a company user, I can see how many users have been discovered and the job status updating live.

Acceptance Criteria:
- Discovery page at `/dashboard/products/{id}/discovery` shows job list
- Active job shows: status badge, users discovered count, start time, elapsed time
- User count updates every 5 seconds while job is running
- After job completes, shows: total users discovered, time taken, "Proceed to NLP" button
- `GET /api/v1/products/{id}/discovery/jobs` returns all jobs with status

---

### Technical Tasks

| ID | Task | Role | Points | Notes |
|---|---|---|---|---|
| S4-BE-1 | `app/ml/discovery/subreddit_map.py`: hardcoded dict mapping interest categories → subreddit names | BE | 2 | e.g., "interior design" → ["r/interiordesign", "r/homedecorating", "r/DIY"]. Start with 30 categories. This is a lookup table, not ML. |
| S4-BE-2 | `app/ml/discovery/reddit_discoverer.py`: `RedditDiscoverer` class | ML | 5 | PRAW setup, `discover_users()`, `_extract_profile()`. Handle: deleted accounts, private accounts, rate limits (sleep on 429). |
| S4-BE-3 | `app/ml/discovery/mock_discoverer.py`: returns users from JSON fixture | ML | 2 | For offline testing. 100 fake users in `tests/fixtures/mock_users.json`. Activated when `REDDIT_CLIENT_ID=mock`. |
| S4-BE-4 | `app/services/discovery_service.py`: `start_discovery()`, `get_jobs()`, `get_job()` | BE | 3 | Creates job row, fires Celery task. |
| S4-BE-5 | `app/workers/tasks/discovery_tasks.py`: `run_discovery_task` | BE | 5 | Full implementation: merge keywords from all motivation categories, call discoverer, bulk insert users, update job counts, trigger content collection on finish. |
| S4-BE-6 | `app/workers/tasks/discovery_tasks.py`: `collect_content_task` | BE | 5 | For each user in job without content: fetch 25 posts via PRAW, store as `user_content` rows, mark `content_collected = true`. Batch: 20 users per task run, re-queue self if more remain. |
| S4-BE-7 | `app/routers/discovery.py`: `POST /products/{id}/discovery/start`, `GET /products/{id}/discovery/jobs`, `GET /products/{id}/discovery/jobs/{job_id}`, `GET /products/{id}/discovery/users` | BE | 3 | Users endpoint paginated: `?page=1&limit=50`. |
| S4-BE-8 | `app/schemas/discovery.py`: `DiscoveryJobResponse`, `DiscoveredUserResponse` | BE | 1 | |
| S4-BE-9 | Mock users JSON fixture: `tests/fixtures/mock_users.json` | ML | 3 | 100 entries with realistic usernames, bios, post arrays matching furniture/home decor interest profile. |
| S4-FE-1 | Discovery page: `src/app/dashboard/products/[id]/discovery/page.tsx` | FE | 2 | Shows job list + active job status + user count. |
| S4-FE-2 | `src/components/discovery/DiscoveryProgress.tsx` | FE | 3 | Progress display: job status badge, animated user count, elapsed timer, progress bar (users_discovered / max_users). Polls every 5s. |
| S4-FE-3 | "Start Discovery" button on product detail page | FE | 2 | Shows modal: confirms max_users (default 300), sources (Reddit checked by default). On confirm: calls `POST .../discovery/start`. |
| S4-FE-4 | `src/lib/hooks/useDiscovery.ts`: `useDiscoveryJobs()`, `useDiscoveryJob(jobId)` | FE | 2 | Job hook polls every 5s when `status === 'running'`. |
| S4-FE-5 | Discovered users table on discovery page | FE | 2 | Columns: username, platform, location, bio (truncated), content_collected badge. Paginated. |

**Sprint 4 Total: 40 points**

---

### Definition of Done for Sprint 4

```
1. Submit product → motivations generated (Sprint 3)
2. Click "Start Discovery"
3. Navigate to /dashboard/products/{id}/discovery
4. Watch user count increase every few seconds
5. After job completes, verify in DB:
   SELECT count(*) FROM discovered_users WHERE product_id = '<id>';
   → at least 50 users (use mock discoverer if Reddit rate limited)
   SELECT count(*) FROM user_content WHERE user_id IN
     (SELECT id FROM discovered_users WHERE product_id = '<id>');
   → at least 200 content rows
   SELECT count(*) FROM discovered_users
     WHERE product_id = '<id>' AND content_collected = true;
   → matches total count (all have content)
```

---

### Risks and Blockers

- **Reddit rate limits:** PRAW has a built-in 60-requests/minute limit. With 300 users × 25 posts = 7,500 API calls. Content collection must use exponential backoff and spread over multiple task invocations. Do NOT try to collect all content in one task run.
- **Empty bios:** Many Reddit users have no bio. This is fine — process posts/comments only. The `user_content` requirement is just "at least 1 piece of text per user."
- **Subreddit map coverage:** The initial 30-category map won't cover every product type. For the demo (furniture), verify these subreddits exist and are active before Sprint 4: `r/interiordesign`, `r/homedecorating`, `r/furniture`, `r/malelivingspace`, `r/femalelivingspace`, `r/DIY`, `r/minimalism`, `r/luxuryhomes`.

---

### What NOT to Build in Sprint 4

- No Twitter/Instagram integration
- No location filtering logic (add post-MVP)
- No NLP yet
- No "stop discovery" UI (the backend endpoint exists, the button can be added in Sprint 8)

---
---

## SPRINT 5
### Theme: Full NLP Pipeline (Embeddings + Empath + BERTopic + spaCy)
### Duration: Weeks 9–10
### Sprint Goal: All discovered users with content have their NLP features computed and stored — embeddings, Empath emotion scores, BERTopic topics, and spaCy entities.

---

### What You Are Building

The text-to-features conversion layer. This sprint transforms raw text into structured signals that the OCEAN scorer and matching engine will use. The four NLP tools must all run correctly and their outputs must be stored in the right tables.

---

### User Stories

**STORY S5-1: NLP pipeline processes all users automatically after content collection**
> As a system, once all users have their content collected, NLP processing begins automatically without manual intervention.

Acceptance Criteria:
- `collect_content_task` (Sprint 4) fires `process_nlp_batch_task` when all content is collected
- Product status advances to `nlp_processing`
- Batch size: 20 users per task invocation, re-queues itself until all users are processed
- Each processed user: `nlp_processed = true`

---

**STORY S5-2: Sentence Transformer embeddings are generated and stored**
> As a system, each user has a 384-dimension embedding generated from their combined text.

Acceptance Criteria:
- Combined text = bio + all posts + all captions, concatenated with space separator
- Text is cleaned before embedding (URLs removed, HTML stripped, whitespace normalized)
- Embedding stored in `user_embeddings` with `embedding_type = 'combined'`
- Model used: `all-MiniLM-L6-v2`
- Embedding is L2-normalized (confirmed via `np.linalg.norm(embedding) ≈ 1.0`)

---

**STORY S5-3: Empath emotional category scores are stored**
> As a system, each user has Empath scores across ~200 emotion/topic categories.

Acceptance Criteria:
- Empath `analyze()` called on combined text with `normalize=True`
- Only non-zero scores stored in `user_nlp_features.empath_scores` (JSONB)
- Top 10 Empath categories extracted as `interest_tags` in `user_nlp_features`
- Zero-score categories are filtered out before storage (reduces JSONB size)

---

**STORY S5-4: BERTopic topics are extracted**
> As a system, each user has topic assignments from BERTopic stored.

Acceptance Criteria:
- BERTopic applied to user's post texts (not combined text — individual posts only)
- Topic assignments stored as `bertopic_topics` JSONB array
- Users with fewer than 2 posts get empty `bertopic_topics` array (BERTopic minimum requirement)
- BERTopic model uses same `all-MiniLM-L6-v2` as the embedding model (no double-loading)

---

**STORY S5-5: spaCy entity extraction and linguistic features are stored**
> As a system, each user has named entities and linguistic metrics extracted and stored.

Acceptance Criteria:
- Entities stored as `[{"text": "Chennai", "label": "GPE"}, ...]` in `spacy_entities`
- `vocabulary_richness` stored as float (unique lemmas / total tokens)
- `avg_sentence_length` stored as float
- `total_tokens` stored as integer

---

### Technical Tasks

| ID | Task | Role | Points | Notes |
|---|---|---|---|---|
| S5-ML-1 | `app/ml/empath_analyzer.py`: `EmpathAnalyzer` singleton with `analyze()` and `get_top_categories()` | ML | 2 | From implementation plan. Singleton avoids reloading Empath lexicon on every call. |
| S5-ML-2 | `app/ml/bertopic_modeler.py`: `TopicModeler` singleton with `get_topics()` | ML | 3 | From implementation plan. Handle `< 2 texts` edge case. Silence BERTopic verbose output. |
| S5-ML-3 | `app/ml/spacy_processor.py`: `SpacyProcessor` singleton with `extract_features()` | ML | 2 | From implementation plan. Load two spaCy pipelines (one with NER, one without for speed on long texts). |
| S5-ML-4 | `app/utils/text_cleaner.py`: complete implementation | BE | 2 | `clean_text(text)`: remove URLs (regex), strip HTML (regex), normalize whitespace, lowercase optional param, handle None → "". |
| S5-BE-1 | `app/services/nlp_service.py`: `process_user_nlp(db, user_id)` | BE | 5 | Full pipeline: get content → clean → embed → empath → bertopic → spacy → store results. From implementation plan. |
| S5-BE-2 | `app/workers/tasks/nlp_tasks.py`: `process_nlp_batch_task(product_id, batch_size=20)` | BE | 3 | Batched Celery task. Fetches 20 unprocessed users, calls `process_user_nlp` for each, re-queues self if more remain. Fires `score_ocean_batch_task` when all done. |
| S5-BE-3 | Wire `collect_content_task` completion → fires `process_nlp_batch_task` | BE | 1 | Add `.delay()` call at end of collect_content_task when all users in job have content. |
| S5-BE-4 | Unit tests: `test_nlp_pipeline.py` | ML | 5 | Test each component independently with fixture text. Test: empty text, non-English text, very long text (>10k chars), text with only URLs. |
| S5-BE-5 | Integration test: full NLP pipeline on 5 mock users | ML | 3 | Use mock_users fixture. Verify all DB rows created correctly. Check embedding shape, empath score count, spacy entity format. |
| S5-FE-1 | User profile page: `src/app/dashboard/products/[id]/discovery/users/[userId]/page.tsx` | FE | 3 | Shows: bio, platform, interest tags (from nlp_features), top Empath categories as bar chart, spaCy entities, OCEAN scores (placeholder for Sprint 6). |
| S5-FE-2 | Discovery page: add NLP progress counter | FE | 2 | Below user count: "NLP Processed: X / Y users" polling every 10s. |

**Sprint 5 Total: 31 points**

---

### Definition of Done for Sprint 5

```bash
# Run full pipeline from product submission through NLP for 20 mock users
# Then verify in DB:

SELECT
  count(*) as total_users,
  count(*) FILTER (WHERE nlp_processed = true) as nlp_done
FROM discovered_users
WHERE product_id = '<id>';
-- Should be: total_users = nlp_done

SELECT user_id, array_length(interest_tags::text[], 1) as tag_count
FROM user_nlp_features LIMIT 5;
-- Should show 5-10 tags per user

SELECT user_id, cardinality(embedding) as dim
FROM user_embeddings LIMIT 5;
-- Should show dim = 384 for all rows

# Also run unit tests:
python -m pytest tests/unit/test_nlp_pipeline.py -v
# All tests pass
```

---

### Risks and Blockers

- **BERTopic memory:** BERTopic with UMAP+HDBSCAN loads 500MB+ into RAM. On Railway's free tier (512MB RAM limit), this will OOM. **Solution:** Use BERTopic in "online" mode or disable UMAP (`umap_model=None`). Test memory usage before this sprint starts.
- **Model loading time:** First invocation of `all-MiniLM-L6-v2` downloads ~90MB. Subsequent Celery tasks reuse the singleton. Ensure model downloads happen at startup, not at task time. Add a health check call in `celery_app.py` startup.
- **Empath compatibility:** `empath==0.89` requires Python 3.8-3.11. Test on Python 3.11 before sprint begins.

---

### What NOT to Build in Sprint 5

- No user-facing NLP feature display beyond the basic tags
- No OCEAN scoring yet
- No matching engine

---
---

## SPRINT 6
### Theme: OCEAN Scoring via Ollama (Batch Processing)
### Duration: Weeks 11–12
### Sprint Goal: Every user who has gone through NLP has an OCEAN score — 5 personality dimensions + confidence — generated by Llama 3.1 and visible in the user profile.

---

### What You Are Building

The personality inference layer. This is where the platform's core differentiation lives. The Llama 3.1 prompt receives a user's bio, posts, and NLP features and returns structured OCEAN scores.

---

### User Stories

**STORY S6-1: OCEAN scoring runs automatically after NLP completes**
> As a system, once NLP processing is complete for all users, OCEAN scoring begins automatically.

Acceptance Criteria:
- `process_nlp_batch_task` fires `score_ocean_batch_task` when all users in a product are NLP-processed
- Product status advances to `ocean_scoring`
- Batch size: 10 users per Celery task invocation (Llama is slow — respect this)
- Task re-queues itself with 5-second delay until all users are scored
- Failed users (Ollama timeout, parse failure) are skipped with error logged — do not block the batch

---

**STORY S6-2: OCEAN scores are generated with valid structure**
> As a system, each user receives a valid OCEAN score with all 5 dimensions and a confidence rating.

Acceptance Criteria:
- All 5 OCEAN dimensions are floats in range [0.0, 10.0]
- Confidence score is a float in range [0.0, 1.0]
- Reasoning text (1 paragraph from LLM) is stored
- Scores are clamped by the parser — a malformed LLM response never crashes the pipeline
- If LLM response cannot be parsed after 2 retries, user is marked `ocean_scored = false` and skipped

---

**STORY S6-3: OCEAN scores are visible in the user profile**
> As a company user, I can open a user's profile and see their OCEAN personality scores displayed visually.

Acceptance Criteria:
- User profile page shows OCEAN scores as a horizontal bar chart (5 bars, 0-10 scale)
- Each bar labeled: Openness, Conscientiousness, Extraversion, Agreeableness, Stability
- Confidence score shown as a percentage badge (e.g., "74% confidence")
- LLM reasoning text shown in a collapsible section
- If OCEAN not yet scored: show "Pending" placeholder

---

### Technical Tasks

| ID | Task | Role | Points | Notes |
|---|---|---|---|---|
| S6-ML-1 | `app/ml/ocean_prompter.py`: `build_ocean_prompt(user_data)` | ML | 3 | Full prompt from implementation plan. Handles empty bio, no posts. Includes Empath top categories and interest tags. |
| S6-ML-2 | `app/ml/ocean_prompter.py`: `parse_ocean_response(text)` | ML | 3 | Regex JSON extraction. Clamp scores. Return None on failure. Validate all 6 required keys exist. |
| S6-BE-1 | `app/services/ocean_service.py`: `score_single_user(db, user)` | BE | 3 | Gather user data → build prompt → call Ollama → parse → store score. From implementation plan. |
| S6-BE-2 | `app/workers/tasks/scoring_tasks.py`: `score_ocean_batch_task(product_id, batch_size=10)` | BE | 5 | Batch Celery task. Skip already-scored users. Skip failed users after 2 parse failures. Re-queue self. Fire `run_matching_task` when all done. |
| S6-BE-3 | Wire NLP batch completion → fires `score_ocean_batch_task` | BE | 1 | Add `.delay()` at end of NLP batch task when no more unprocessed users remain. |
| S6-BE-4 | `app/routers/users.py`: `GET /products/{id}/discovery/users/{user_id}` returning full profile with OCEAN | BE | 2 | Join: discovered_user + user_ocean_scores + user_nlp_features + user_content (sample). |
| S6-BE-5 | `app/schemas/user.py`: `UserProfileResponse` with nested OCEAN and NLP fields | BE | 2 | |
| S6-BE-6 | Unit tests: `test_ocean_prompter.py` | ML | 3 | Valid response parse, clamping out-of-range scores, malformed JSON → None, missing keys → None, extra text before JSON → parse succeeds. |
| S6-BE-7 | Ollama timeout handling + retry in `llm_client.py` | ML | 2 | If httpx timeout (120s): retry once with shorter context (trim posts). Second failure: return None. |
| S6-FE-1 | OCEAN bar chart component: `src/components/leads/OceanBarChart.tsx` | FE | 2 | 5 horizontal bars, 0-10 scale. Different color shade per dimension. Labels left, value right. |
| S6-FE-2 | Update user profile page with OCEAN bar chart, confidence badge, reasoning (collapsible) | FE | 2 | Conditional render: if `ocean` null → "Awaiting scoring..." skeleton. |
| S6-FE-3 | Discovery page: add OCEAN scoring progress counter | FE | 1 | "OCEAN Scored: X / Y" polling every 15s (scoring is slow). |

**Sprint 6 Total: 29 points**

---

### Definition of Done for Sprint 6

```
1. Run full pipeline through OCEAN scoring on 20 mock users
2. Open any user's profile in the dashboard
3. See OCEAN bar chart with 5 different score values
4. See confidence badge showing 30-85%
5. See reasoning paragraph from Llama

# DB verification:
SELECT count(*) FROM user_ocean_scores WHERE user_id IN
  (SELECT id FROM discovered_users WHERE product_id = '<id>');
-- Should equal total discovered users (minus any parse failures)

SELECT openness, conscientiousness, extraversion, agreeableness, emotional_stability
FROM user_ocean_scores LIMIT 5;
-- All values between 0 and 10, all different (not the same defaults)

# Unit tests:
python -m pytest tests/unit/test_ocean_prompter.py -v
-- All tests pass
```

---

### Risks and Blockers

- **Ollama throughput:** Llama 3.1 8B on Oracle VM processes one request at a time. 300 users × 60-90 seconds each = 5-7 hours. This is normal for the MVP. The batch task handles it without blocking the API. If faster scoring is needed post-MVP, use multiple Oracle VMs or switch to a cloud LLM API.
- **Parse failures:** In production tests, expect 5-15% of LLM responses to fail parsing. The batch task must skip these gracefully. Log failures to a structured log file for post-analysis.
- **Context length:** Users with 25 long posts may exceed Llama's context window. Trim posts to 300 characters each before building the prompt (already specified in plan).

---
---

## SPRINT 7
### Theme: Matching Engine + Lead Ranking + Leads Dashboard
### Duration: Weeks 13–14
### Sprint Goal: A company can open their product's leads page and see a ranked, tiered table of leads — each with a compatibility score, matched motivation category, and clickable profile drawer.

---

### What You Are Building

The intelligence output. This sprint produces the ranked lead list that justifies the entire platform. The matching engine scores every user against every motivation category. The ranking engine collapses these into one lead per user. The leads page presents the results.

---

### User Stories

**STORY S7-1: Matching engine runs automatically after OCEAN scoring**
> As a system, once all users are OCEAN-scored, the matching engine runs automatically.

Acceptance Criteria:
- `score_ocean_batch_task` fires `run_matching_task` when all users in product are scored
- Product status advances to `matching`
- For each user × each motivation category: one `lead_matches` row created
- All 4 score components (personality, interest, activity, confidence) stored
- Compatibility score = weighted sum as per plan (40/35/15/10)

---

**STORY S7-2: Lead ranking produces a tiered lead list**
> As a system, after matching, leads are ranked and assigned tiers (Hot, Warm, Cold).

Acceptance Criteria:
- One `leads` row per (user, product) pair
- Rank = integer starting at 1 (1 = best match)
- Tier: top 15% = Hot, next 35% = Warm, remaining 50% = Cold
- `best_motivation_category_id` = the category with highest compatibility score for that user
- Product status advances to `completed` after ranking finishes

---

**STORY S7-3: Leads are displayed in a ranked, filterable table**
> As a company user, I can see my ranked leads in a table with filters, sort by score, and identify hot leads immediately.

Acceptance Criteria:
- Leads table at `/dashboard/products/{id}/leads` loads in under 3 seconds
- Default sort: by rank (ascending)
- Columns: Rank, Username, Platform, Best Motivation Match, Score (progress bar), Tier badge, Status
- Filters: tier (Hot/Warm/Cold), status (new/viewed/contacted), min score slider
- Pagination: 20 per page
- Clicking any row opens the Lead Drawer

---

**STORY S7-4: Lead Drawer shows full psychographic profile**
> As a company user, I can open a lead's profile and see everything about why they match — their OCEAN scores, matched motivation, score breakdown, and a link to their profile.

Acceptance Criteria:
- Slide-in drawer (Sheet component from shadcn)
- Header: username, platform badge, "View Profile" external link
- Bio text (full, not truncated)
- Matched motivation category name + description
- OCEAN radar chart (both user scores and target category scores overlaid)
- Score breakdown: 4 components as labeled percentage bars
- Status dropdown: New → Viewed → Contacted → Converted / Rejected
- Status change calls `PATCH /leads/{lead_id}`

---

**STORY S7-5: Leads can be exported as CSV**
> As a company, I can download my lead list as a CSV file for use in other tools.

Acceptance Criteria:
- `GET /api/v1/products/{id}/leads/export` returns CSV with Content-Disposition header
- Columns: rank, username, platform, profile_url, bio, compatibility_score, tier, best_motivation, openness, conscientiousness, extraversion, agreeableness, emotional_stability
- Frontend "Export CSV" button triggers download

---

### Technical Tasks

| ID | Task | Role | Points | Notes |
|---|---|---|---|---|
| S7-BE-1 | `app/services/matching_service.py`: all 4 score functions | BE | 3 | From implementation plan: `calculate_personality_match`, `calculate_interest_match`, `calculate_activity_score`, `calculate_compatibility`. |
| S7-BE-2 | `app/workers/tasks/matching_tasks.py`: `run_matching_task(product_id)` | BE | 5 | Full N×M matching. Load users in batches of 50. For each user: join OCEAN + embedding. For each category: join profile + embedding. Compute all 4 scores. Bulk insert `lead_matches`. |
| S7-BE-3 | `app/workers/tasks/matching_tasks.py`: `rank_leads_task(product_id)` | BE | 3 | SQL `DISTINCT ON` to get best match per user. Sort by compatibility DESC. Assign ranks + tiers. Bulk insert `leads`. Update product status. |
| S7-BE-4 | Wire matching completion → fires `rank_leads_task` | BE | 1 | At end of `run_matching_task`. |
| S7-BE-5 | `app/routers/leads.py`: all 5 lead endpoints | BE | 3 | `GET /leads` (paginated, filterable), `GET /leads/{id}`, `PATCH /leads/{id}`, `GET /leads/export`, `GET /leads/stats` |
| S7-BE-6 | `app/schemas/lead.py`: `LeadResponse`, `LeadDetail`, `LeadStats` | BE | 2 | `LeadDetail` includes nested user, OCEAN scores, match details, motivation category. |
| S7-BE-7 | CSV export: `GET /products/{id}/leads/export` | BE | 2 | Use Python `csv` module + `StreamingResponse`. |
| S7-BE-8 | `GET /products/{id}/leads/stats`: tier counts + score histogram | BE | 2 | Returns `{hot: N, warm: N, cold: N, score_histogram: [{range, count}]}`. |
| S7-BE-9 | Unit tests: matching engine score functions | BE | 3 | From implementation plan test cases. Add: activity score with 0 followers, identical OCEAN = 1.0, maximum distance = 0.0. |
| S7-FE-1 | Leads page: `src/app/dashboard/products/[id]/leads/page.tsx` | FE | 2 | Layout: filter bar + table + pagination. |
| S7-FE-2 | `src/components/leads/LeadsTable.tsx` | FE | 5 | From implementation plan. Sortable columns, tier filter chips, score filter slider, paginated rows, click → open drawer. |
| S7-FE-3 | `src/components/leads/TierBadge.tsx` | FE | 1 | Hot = red, Warm = orange, Cold = blue. |
| S7-FE-4 | `src/components/leads/LeadDrawer.tsx` | FE | 5 | Sheet component. 4 sections: profile header, motivation match, OCEAN dual-overlay radar, score breakdown + status. |
| S7-FE-5 | Dual-overlay OCEAN radar in LeadDrawer | FE | 3 | Two `<Radar>` series in one `<RadarChart>`: user (solid) + target category (dashed). Legend: "Your Lead" vs "Target Profile". |
| S7-FE-6 | `src/lib/hooks/useLeads.ts`: `useLeads(productId, filters)`, `useLead(leadId)`, `useLeadStats(productId)` | FE | 2 | |
| S7-FE-7 | Export CSV button: triggers `GET .../leads/export` as file download | FE | 1 | `window.location.href = api_url + '/export'` pattern with API key in URL param (for file download). |
| S7-FE-8 | `src/app/dashboard/products/[id]/analytics/page.tsx`: tier donut chart + score histogram | FE | 3 | Uses `useLeadStats`. Recharts `PieChart` for tier distribution. Bar chart for score histogram. |

**Sprint 7 Total: 46 points**

---

### Definition of Done for Sprint 7

```
Full end-to-end test with real (or mock) data:

1. Complete pipeline: product → motivations → discovery → NLP → OCEAN → matching → ranking
2. Open /dashboard/products/{id}/leads
3. See at least 30 leads ranked 1 to N
4. Top lead has compatibility_score > 0.65
5. Hot/Warm/Cold tier distribution makes sense visually
6. Click lead #1 → drawer opens with OCEAN radar + motivation label
7. Change status to "Contacted" → refreshes, drawer still open, status updated
8. Click "Export CSV" → file downloads, opens in spreadsheet with correct columns

# DB verification:
SELECT tier, count(*) FROM leads WHERE product_id = '<id>' GROUP BY tier;
-- hot: ~15%, warm: ~35%, cold: ~50% of total

SELECT count(*) FROM lead_matches WHERE product_id = '<id>';
-- Should be: users_count × motivation_categories_count (e.g., 50 × 5 = 250)

# Unit tests:
python -m pytest tests/unit/test_matching_engine.py -v
-- All tests pass
```

---
---

## SPRINT 8
### Theme: Dashboard Polish + Testing + Deployment
### Duration: Weeks 15–16
### Sprint Goal: The platform is deployed, accessible via public URL, smoke-tested end-to-end, and ready for a live demo.

---

### What You Are Building

Production readiness. No new features — only polish, hardening, and deployment. This sprint pays technical debt from all previous sprints and gets the platform in front of real users.

---

### User Stories

**STORY S8-1: Dashboard home shows a meaningful overview**
> As a company user, the first page I see after login gives me an at-a-glance summary of all my products and top leads.

Acceptance Criteria:
- Stats cards: Total Products, Total Leads Discovered, Hot Leads, Pipeline Running
- Recent activity feed: last 10 events (job started, leads ranked, etc.)
- Top 3 hot leads across all products (linking to their lead pages)

---

**STORY S8-2: All error states are handled gracefully**
> As a user, I never see a white error screen or a raw stack trace.

Acceptance Criteria:
- Every page has an error boundary
- Empty states: product list with 0 products, leads with 0 results, discovery with no job
- Loading skeletons on all data-fetching pages (no blank flashes)
- Pipeline failure state: product detail shows error message with "Retry" button

---

**STORY S8-3: Platform is deployed and accessible**
> As a company, I can access the platform via a public URL without running anything locally.

Acceptance Criteria:
- Backend deployed on Railway: FastAPI + Celery worker + Redis + PostgreSQL
- Frontend deployed on Vercel
- Ollama running on Oracle VM, reachable from Railway
- Environment variables set correctly on both platforms
- `GET https://api.psycholead.app/health` returns 200
- `https://psycholead.vercel.app` loads the dashboard

---

**STORY S8-4: Full end-to-end integration test suite passes**
> As a team, we can run one command that tests the complete pipeline with mock data.

Acceptance Criteria:
- `pytest tests/e2e/test_full_pipeline.py` completes without failures
- Uses mock discoverer + mock LLM responses (no real API calls)
- Tests: company creation → product → motivations → discovery → NLP → OCEAN → matching → ranking → leads accessible
- GitHub Actions CI runs this on every push to main

---

### Technical Tasks

| ID | Task | Role | Points | Notes |
|---|---|---|---|---|
| S8-BE-1 | `GET /api/v1/dashboard/overview` endpoint | BE | 2 | Returns: product count, total leads, hot leads count, any running pipeline jobs. |
| S8-BE-2 | `GET /api/v1/dashboard/recent-activity` endpoint | BE | 2 | Derive from `discovery_jobs` + `products` updated_at. Return last 10 events as list of `{event_type, product_name, timestamp}`. |
| S8-BE-3 | `POST /api/v1/products/{id}/restart` — retry failed pipeline | BE | 2 | Detect last completed step from `pipeline_step`, re-fire the appropriate Celery task. |
| S8-BE-4 | `DELETE /api/v1/products/{id}` — cascade delete | BE | 1 | PostgreSQL cascades handle child rows. Update product status to deleted. |
| S8-BE-5 | E2E test: `tests/e2e/test_full_pipeline.py` | BE | 8 | Uses fixtures. Mocks Ollama and Reddit. Runs full pipeline via Celery `CELERY_TASK_ALWAYS_EAGER=True`. Asserts all DB states. |
| S8-BE-6 | GitHub Actions CI: `.github/workflows/ci.yml` | BE | 2 | PostgreSQL + Redis services. Run unit tests + integration tests. |
| S8-BE-7 | `backend/Dockerfile` production build | BE | 2 | Multi-stage build. spaCy model download baked in. Non-root user. |
| S8-BE-8 | Railway deployment: FastAPI service + Celery worker service | FS | 3 | Two Railway services from same repo. Different start commands. Shared env vars via Railway env groups. |
| S8-BE-9 | PostgreSQL pgvector activation on Railway | BE | 1 | Connect via Railway psql shell: `CREATE EXTENSION vector;`. Run `alembic upgrade head`. |
| S8-BE-10 | Oracle VM: Ollama as systemd service, Nginx reverse proxy | FS | 2 | Open port, create service file, test from Railway curl. |
| S8-FE-1 | Dashboard home page: `src/app/dashboard/page.tsx` | FE | 3 | Stats cards + recent activity + top leads widget. Uses `useDashboard()` hook polling every 30s. |
| S8-FE-2 | `src/components/dashboard/StatsCards.tsx` | FE | 2 | 4 cards. Recharts `Sparkline` inside each card (optional). |
| S8-FE-3 | `src/components/dashboard/RecentActivityFeed.tsx` | FE | 2 | Timeline list with icons per event type. |
| S8-FE-4 | Error boundaries on all pages | FE | 2 | Next.js `error.tsx` in each route segment. Shows friendly message + retry button. |
| S8-FE-5 | Loading skeletons on: product list, leads table, motivations page | FE | 2 | shadcn Skeleton component. Match exact layout of loaded state. |
| S8-FE-6 | Empty states: product list (0 products), leads (0 results), discovery (no jobs) | FE | 2 | Centered illustration (SVG) + helpful text + primary action button. |
| S8-FE-7 | Mobile responsiveness audit | FE | 2 | Test on 375px (iPhone SE) and 768px (tablet). Fix: sidebar collapses, table scrolls horizontally, drawer full-screen on mobile. |
| S8-FE-8 | Vercel deployment + env vars | FE | 1 | Connect GitHub repo. Set `NEXT_PUBLIC_API_URL`. Deploy. |
| S8-FS-1 | Full smoke test on production environment | FS | 3 | End-to-end: register → submit product → wait for pipeline → view leads. Document any production-only bugs. Fix 2 highest severity ones. |

**Sprint 8 Total: 44 points**

---

### Definition of Done for Sprint 8 (= MVP Complete)

```
Production verification:

1. https://psycholead.vercel.app loads
2. Register new company → receive API key
3. Submit "Premium Sofa" product
4. Wait for pipeline (status polling works)
5. See 5 motivation categories
6. Start discovery (uses mock if Reddit rate limited)
7. See NLP + OCEAN scoring progress
8. See ranked leads page with Hot/Warm/Cold tiers
9. Open lead drawer → see full profile with dual-overlay radar chart
10. Export CSV → file downloads

All CI tests pass:
pytest tests/ -v → 0 failures

Railway health check:
curl https://<railway-url>/health → {"status":"ok","db":"connected","redis":"connected"}
```

---

## Summary: Sprint-by-Sprint At a Glance

| Sprint | Theme | Key Output | Total Points |
|---|---|---|---|
| 1 | Foundation | DB + project skeleton | 36 |
| 2 | Company + Product APIs + Submission UI | Company registers, submits product | 45 |
| 3 | Motivation Generation + UI | Llama generates buyer personas | 39 |
| 4 | User Discovery + Content Collection | Reddit users + posts in DB | 40 |
| 5 | NLP Pipeline | Embeddings + Empath + topics + entities | 31 |
| 6 | OCEAN Scoring | Personality scores via Llama | 29 |
| 7 | Matching + Ranking + Leads UI | Ranked lead list with drawer | 46 |
| 8 | Polish + Testing + Deployment | Live production platform | 44 |
| **Total** | | | **310 points** |

---

## What to Build First (Strict Order)

If you start tomorrow, build these 5 things in this exact order. Nothing else:

```
1. docker-compose.yml  ← gets every dev unblocked in under 30 minutes
2. SQLAlchemy models   ← all 12, even rough. Alembic migration from them.
3. FastAPI /health     ← proves DB + Redis connection works
4. POST /companies     ← proves auth pattern works
5. POST /products      ← proves the core entity exists
```

Everything else depends on these five. Do not start the frontend, NLP setup, or Ollama configuration until all five are done and tested.

---

## Pre-Sprint Checklist (Do Before Any Code)

- [ ] GitHub repository created (private), all team members added
- [ ] Docker Desktop installed on all developer machines
- [ ] Python 3.11 installed (`python --version`)
- [ ] Node.js 20+ installed (`node --version`)
- [ ] PostgreSQL client installed (psql or TablePlus/DBeaver for visual inspection)
- [ ] Oracle Free Tier VM created (Ubuntu 22.04, 4GB RAM shape)
- [ ] Reddit developer app registered at reddit.com/prefs/apps
- [ ] `.env` file created from `.env.example` with real values
- [ ] Ollama installation confirmed on Oracle VM (`ollama list` shows `llama3.1:8b`)

---

*Backlog version: 1.0 — Derived from IMPLEMENTATION_PLAN.md*
*8 Sprints × 2 Weeks = 16 Weeks to MVP*
*Total: 310 story points across 8 sprints*
