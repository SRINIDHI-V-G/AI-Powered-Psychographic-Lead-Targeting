"""
Phase C NLP Pipeline — test suite.

Coverage:
  Unit tests (no DB, no network):
    - text_cleaner: clean_text, combine_user_content
    - text_processor: extract_features
    - empath_analyzer: EmpathAnalyzer.analyze, get_top_categories
    - embeddings: EmbeddingModel.encode shape + cosine_similarity
    - bertopic_modeler: TopicModeler graceful fallback

  Service / integration tests (in-memory SQLite via async SQLAlchemy):
    - process_user_nlp: full pipeline per user, produces embedding + features
    - run_nlp_for_product: batch processing, marks all users nlp_processed

  API tests (FastAPI TestClient, SQLite in-memory):
    - GET  /products/{id}/nlp/status   → 200 with correct counts
    - POST /products/{id}/nlp/trigger  → 202 queued
    - GET  /products/{id}/discovery/users/{uid}/nlp → 404 before processing

Run with:
  cd backend && pytest tests/test_phase_c.py -v
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio


# ═══════════════════════════════════════════════════════════════════════════════
# 1. TEXT CLEANER — unit tests
# ═══════════════════════════════════════════════════════════════════════════════

from app.ml.nlp.text_cleaner import clean_text, combine_user_content


class TestCleanText:
    def test_none_returns_empty(self):
        assert clean_text(None) == ""

    def test_empty_string(self):
        assert clean_text("") == ""

    def test_removes_url(self):
        result = clean_text("Visit https://example.com for more")
        assert "https" not in result
        assert "example.com" not in result

    def test_removes_html_tags(self):
        result = clean_text("<b>Bold</b> and <i>italic</i>")
        assert "<b>" not in result
        assert "Bold" in result

    def test_removes_reddit_artifacts(self):
        result = clean_text("[deleted] Some content [removed]")
        assert "[deleted]" not in result
        assert "[removed]" not in result

    def test_collapses_repeated_punctuation(self):
        result = clean_text("Wow!!!!! Really???")
        assert "!!!" not in result

    def test_collapses_whitespace(self):
        result = clean_text("too   many    spaces")
        assert "  " not in result

    def test_lowercase_flag(self):
        result = clean_text("Hello WORLD", lowercase=True)
        assert result == "hello world"

    def test_unicode_normalisation(self):
        # fancy quotes → regular
        result = clean_text("“Hello”")
        assert result  # should not crash and should return something


class TestCombineUserContent:
    def test_bio_plus_posts(self):
        result = combine_user_content("I love tech", ["Post one", "Post two"])
        assert "I love tech" in result
        assert "Post one" in result
        assert "Post two" in result

    def test_none_bio(self):
        result = combine_user_content(None, ["Only a post"])
        assert "Only a post" in result

    def test_empty_content_list(self):
        result = combine_user_content("Just a bio", [])
        assert "Just a bio" in result

    def test_all_empty(self):
        result = combine_user_content(None, [])
        assert result == ""

    def test_filters_empty_posts(self):
        result = combine_user_content("bio", ["", "   ", "real post"])
        assert "real post" in result
        # whitespace-only strings should not add trailing spaces
        assert not result.startswith(" ")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. TEXT PROCESSOR — unit tests
# ═══════════════════════════════════════════════════════════════════════════════

from app.ml.nlp.text_processor import extract_features


class TestExtractFeatures:
    def test_empty_string(self):
        result = extract_features("")
        assert result["total_tokens"] == 0
        assert result["vocabulary_richness"] == 0.0
        assert result["entities"] == []
        assert result["keyword_frequency"] == {}

    def test_basic_metrics(self):
        text = "The quick brown fox jumps over the lazy dog."
        result = extract_features(text)
        assert result["total_tokens"] > 0
        assert 0.0 < result["vocabulary_richness"] <= 1.0
        assert result["avg_sentence_length"] > 0

    def test_keyword_frequency_excludes_stopwords(self):
        text = "machine learning is great and machine learning is powerful"
        result = extract_features(text)
        freq = result["keyword_frequency"]
        # "machine" and "learning" should appear; "is" and "and" should not
        assert "machine" in freq
        assert "learning" in freq
        assert "is" not in freq

    def test_top_20_limit(self):
        # Generate a long document with many distinct content words
        words = [f"word{i}" for i in range(50)]
        text = " ".join(words)
        result = extract_features(text)
        assert len(result["keyword_frequency"]) <= 20

    def test_city_entity_extraction(self):
        text = "I live in Chennai and work in Bangalore."
        result = extract_features(text)
        labels = [e["label"] for e in result["entities"]]
        texts = [e["text"].lower() for e in result["entities"]]
        assert "GPE" in labels
        assert "chennai" in texts

    def test_org_entity_extraction(self):
        text = "I work at Infosys Technologies and previously at Wipro Ltd."
        result = extract_features(text)
        org_labels = [e for e in result["entities"] if e["label"] == "ORG"]
        assert len(org_labels) > 0

    def test_vocabulary_richness_range(self):
        # All unique words → richness close to 1.0
        text = "alpha beta gamma delta epsilon"
        result = extract_features(text)
        assert result["vocabulary_richness"] > 0.5


# ═══════════════════════════════════════════════════════════════════════════════
# 3. EMPATH ANALYZER — unit tests
# ═══════════════════════════════════════════════════════════════════════════════

from app.ml.nlp.empath_analyzer import EmpathAnalyzer


class TestEmpathAnalyzer:
    def setup_method(self):
        # Reset singleton between tests
        EmpathAnalyzer._instance = None
        EmpathAnalyzer._lexicon = None
        self.analyzer = EmpathAnalyzer()

    def test_empty_text_returns_empty_dict(self):
        result = self.analyzer.analyze("")
        assert result == {}

    def test_none_text_returns_empty_dict(self):
        result = self.analyzer.analyze(None)  # type: ignore[arg-type]
        assert result == {}

    def test_scores_are_floats(self):
        result = self.analyzer.analyze("I love spending time with my family.")
        assert all(isinstance(v, float) for v in result.values())

    def test_scores_are_positive(self):
        result = self.analyzer.analyze("I love technology and innovation.")
        assert all(v > 0 for v in result.values())

    def test_minimum_score_filter(self):
        # All returned scores should be above the minimum threshold (0.001)
        result = self.analyzer.analyze("technology startup innovation growth")
        assert all(v > 0.001 for v in result.values())

    def test_get_top_categories_order(self):
        scores = {"tech": 0.8, "affection": 0.3, "achievement": 0.9, "food": 0.1}
        top = self.analyzer.get_top_categories(scores, n=2)
        assert top[0] == "achievement"
        assert top[1] == "tech"

    def test_get_top_categories_respects_n(self):
        scores = {f"cat{i}": float(i) for i in range(20)}
        top = self.analyzer.get_top_categories(scores, n=5)
        assert len(top) == 5

    def test_singleton_pattern(self):
        a = EmpathAnalyzer()
        b = EmpathAnalyzer()
        assert a is b

    def test_interest_tags_from_real_text(self):
        text = "I enjoy hiking mountains and outdoor adventures with friends"
        scores = self.analyzer.analyze(text)
        tags = self.analyzer.get_top_categories(scores, n=10)
        assert isinstance(tags, list)
        assert len(tags) <= 10
        assert all(isinstance(t, str) for t in tags)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. EMBEDDING MODEL — unit tests
# ═══════════════════════════════════════════════════════════════════════════════

from app.ml.nlp.embeddings import EmbeddingModel


class TestEmbeddingModel:
    def setup_method(self):
        EmbeddingModel._instance = None
        EmbeddingModel._model = None

    def test_encode_returns_384_dims(self):
        model = EmbeddingModel()
        vec = model.encode("Hello world")
        assert len(vec) == 384

    def test_encode_returns_list_of_floats(self):
        model = EmbeddingModel()
        vec = model.encode("Test sentence")
        assert all(isinstance(v, float) for v in vec)

    def test_empty_text_returns_zero_vector(self):
        model = EmbeddingModel()
        vec = model.encode("")
        assert len(vec) == 384
        assert all(v == 0.0 for v in vec)

    def test_unit_vector_normalisation(self):
        import math
        model = EmbeddingModel()
        vec = model.encode("Machine learning is fascinating")
        norm = math.sqrt(sum(v * v for v in vec))
        assert abs(norm - 1.0) < 0.01  # L2-normalised

    def test_cosine_similarity_identical(self):
        model = EmbeddingModel()
        vec = model.encode("Identical text")
        sim = EmbeddingModel.cosine_similarity(vec, vec)
        assert abs(sim - 1.0) < 0.01

    def test_cosine_similarity_different(self):
        model = EmbeddingModel()
        vec_a = model.encode("I love hiking and outdoor sports")
        vec_b = model.encode("Financial markets and stock trading")
        sim = EmbeddingModel.cosine_similarity(vec_a, vec_b)
        # Should be less than 1.0 for semantically different texts
        assert sim < 0.99

    def test_cosine_similarity_similar_texts(self):
        model = EmbeddingModel()
        vec_a = model.encode("I enjoy outdoor hiking in mountains")
        vec_b = model.encode("Hiking and trekking in the hills is my passion")
        sim = EmbeddingModel.cosine_similarity(vec_a, vec_b)
        # Similar texts should have higher similarity than random
        assert sim > 0.3

    def test_encode_batch(self):
        model = EmbeddingModel()
        texts = ["First sentence", "Second sentence", "Third sentence"]
        vecs = model.encode_batch(texts)
        assert len(vecs) == 3
        assert all(len(v) == 384 for v in vecs)

    def test_encode_batch_empty(self):
        model = EmbeddingModel()
        result = model.encode_batch([])
        assert result == []

    def test_singleton_pattern(self):
        a = EmbeddingModel()
        b = EmbeddingModel()
        assert a is b


# ═══════════════════════════════════════════════════════════════════════════════
# 5. BERTOPIC MODELER — unit tests (graceful fallback)
# ═══════════════════════════════════════════════════════════════════════════════

from app.ml.nlp.bertopic_modeler import TopicModeler


class TestTopicModeler:
    def setup_method(self):
        TopicModeler._instance = None
        TopicModeler._model = None
        TopicModeler._available = None

    def test_singleton_pattern(self):
        a = TopicModeler()
        b = TopicModeler()
        assert a is b

    def test_too_few_texts_returns_empty(self):
        modeler = TopicModeler()
        result = modeler.get_topics(["Only one text"])
        assert result == []

    def test_empty_list_returns_empty(self):
        modeler = TopicModeler()
        result = modeler.get_topics([])
        assert result == []

    def test_unavailable_bertopic_returns_empty(self):
        modeler = TopicModeler()
        modeler._available = False  # simulate bertopic not installed
        result = modeler.get_topics(["text one", "text two", "text three"])
        assert result == []

    def test_return_format_when_available(self):
        # Mock bertopic availability and model
        modeler = TopicModeler()
        modeler._available = True

        mock_model = MagicMock()
        mock_model.fit_transform.return_value = ([0, 1, 0], [0.9, 0.8, 0.7])
        modeler._model = mock_model

        texts = ["text about tech", "text about food", "text about tech again"]
        result = modeler.get_topics(texts)

        assert len(result) == 3
        assert all("topic_id" in r and "probability" in r for r in result)
        assert all(isinstance(r["topic_id"], int) for r in result)
        assert all(isinstance(r["probability"], float) for r in result)

    def test_bertopic_exception_returns_empty(self):
        modeler = TopicModeler()
        modeler._available = True

        mock_model = MagicMock()
        mock_model.fit_transform.side_effect = RuntimeError("OOM")
        modeler._model = mock_model

        result = modeler.get_topics(["a", "b", "c"])
        assert result == []


# ═══════════════════════════════════════════════════════════════════════════════
# 6. NLP SERVICE — mocked async tests
#
# Models use PostgreSQL-specific JSONB/UUID types — SQLite can't run DDL.
# We mock the AsyncSession instead.
# ═══════════════════════════════════════════════════════════════════════════════

from unittest.mock import AsyncMock
from app.models.discovery import DiscoveredUser, UserContent
from app.models.nlp import UserEmbedding, UserNlpFeatures
from app.models.product import Product, PriceRange, ProductStatus
from app.models.company import Company
from app.services.nlp_service import process_user_nlp, run_nlp_for_product


def _mock_user(user_id: uuid.UUID, product_id: uuid.UUID, *, nlp_processed: bool = False, bio: str | None = "I love ML") -> MagicMock:
    u = MagicMock(spec=DiscoveredUser)
    u.id = user_id
    u.product_id = product_id
    u.username = "testuser"
    u.bio = bio
    u.nlp_processed = nlp_processed
    return u


def _mock_content_items(texts: list[str]) -> list[MagicMock]:
    items = []
    for t in texts:
        item = MagicMock(spec=UserContent)
        item.content_type = "post"
        item.content_text = t
        items.append(item)
    return items


def _make_mock_db(user: MagicMock, content_items: list) -> AsyncMock:
    """Build a minimal AsyncSession mock for the NLP service."""
    db = AsyncMock()
    db.get.return_value = user

    # db.execute() call 1: fetch UserContent
    content_scalars = MagicMock()
    content_scalars.scalars.return_value.all.return_value = content_items
    # db.execute() calls 2 and 3: check for existing embedding / nlp_features
    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None

    db.execute.side_effect = [content_scalars, no_existing, no_existing]
    return db


@pytest.mark.asyncio
async def test_process_user_nlp_success():
    user_id = uuid.uuid4()
    product_id = uuid.uuid4()
    content = _mock_content_items([
        "Working on deep learning projects every day.",
        "Python is my favourite language for data science.",
        "Excited about the future of artificial intelligence.",
    ])
    user = _mock_user(user_id, product_id)
    db = _make_mock_db(user, content)

    result = await process_user_nlp(db, user_id)

    assert result is True
    assert user.nlp_processed is True
    # Should have added UserEmbedding + UserNlpFeatures
    assert db.add.call_count == 2
    added_types = [type(call.args[0]).__name__ for call in db.add.call_args_list]
    assert "UserEmbedding" in added_types
    assert "UserNlpFeatures" in added_types


@pytest.mark.asyncio
async def test_process_user_nlp_embedding_is_384_dims():
    user_id = uuid.uuid4()
    product_id = uuid.uuid4()
    content = _mock_content_items(["Deep learning is amazing.", "Python for AI."])
    user = _mock_user(user_id, product_id)
    db = _make_mock_db(user, content)

    await process_user_nlp(db, user_id)

    embedding_call = next(
        call for call in db.add.call_args_list
        if isinstance(call.args[0], UserEmbedding)
    )
    embedding_obj: UserEmbedding = embedding_call.args[0]
    assert len(embedding_obj.embedding) == 384


@pytest.mark.asyncio
async def test_process_user_nlp_already_processed():
    user_id = uuid.uuid4()
    user = _mock_user(user_id, uuid.uuid4(), nlp_processed=True)
    db = AsyncMock()
    db.get.return_value = user

    result = await process_user_nlp(db, user_id)

    assert result is False
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_process_user_nlp_user_not_found():
    db = AsyncMock()
    db.get.return_value = None

    result = await process_user_nlp(db, uuid.uuid4())

    assert result is False


@pytest.mark.asyncio
async def test_process_user_nlp_no_content():
    user_id = uuid.uuid4()
    user = _mock_user(user_id, uuid.uuid4(), bio=None)
    db = _make_mock_db(user, [])  # no content items

    result = await process_user_nlp(db, user_id)

    assert result is False
    assert user.nlp_processed is True  # marked to prevent retry


@pytest.mark.asyncio
async def test_process_user_nlp_interest_tags_populated():
    user_id = uuid.uuid4()
    content = _mock_content_items([
        "I love hiking and outdoor adventures.",
        "Camping is the best way to relax.",
    ])
    user = _mock_user(user_id, uuid.uuid4())
    db = _make_mock_db(user, content)

    await process_user_nlp(db, user_id)

    nlp_call = next(
        call for call in db.add.call_args_list
        if isinstance(call.args[0], UserNlpFeatures)
    )
    nlp_obj: UserNlpFeatures = nlp_call.args[0]
    assert isinstance(nlp_obj.interest_tags, list)
    assert isinstance(nlp_obj.empath_scores, dict)
    assert nlp_obj.total_tokens > 0


@pytest.mark.asyncio
async def test_run_nlp_for_product_processes_all_users():
    product_id = uuid.uuid4()
    user_ids = [uuid.uuid4() for _ in range(3)]

    # Mock the initial query that returns user IDs
    db = AsyncMock()
    id_result = MagicMock()
    id_result.fetchall.return_value = [(uid,) for uid in user_ids]
    db.execute.return_value = id_result

    # Mock db.get() to return a not-yet-processed user each time
    def make_user(uid: uuid.UUID) -> MagicMock:
        u = MagicMock(spec=DiscoveredUser)
        u.id = uid
        u.username = f"user_{uid.hex[:6]}"
        u.bio = "I love technology and software development."
        u.nlp_processed = False
        return u

    users = {uid: make_user(uid) for uid in user_ids}
    db.get.side_effect = lambda model, uid: users.get(uid)

    # Content execute calls need to return items for each user (3 users × 3 calls each)
    content = _mock_content_items(["Post about tech.", "Another post about AI."])

    content_result = MagicMock()
    content_result.scalars.return_value.all.return_value = content
    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None

    # Pattern per user: content_result, no_existing, no_existing
    side_effects = []
    for _ in user_ids:
        side_effects.extend([content_result, no_existing, no_existing])
    db.execute.side_effect = [id_result] + side_effects

    summary = await run_nlp_for_product(db, product_id)

    assert summary["total"] == 3
    assert summary["processed"] == 3
    assert summary["failed"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 7. API LAYER — FastAPI endpoint tests (mocked CRUD + auth)
# ═══════════════════════════════════════════════════════════════════════════════

import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import get_db
from app.dependencies import get_current_company


def _fake_company() -> MagicMock:
    co = MagicMock(spec=Company)
    co.id = uuid.uuid4()
    co.name = "Test Co"
    return co


def _fake_product(company_id: uuid.UUID, status: str = "discovering") -> MagicMock:
    p = MagicMock(spec=Product)
    p.id = uuid.uuid4()
    p.company_id = company_id
    p.status = MagicMock()
    p.status.value = status
    return p


@pytest_asyncio.fixture
async def api_client():
    company = _fake_company()
    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    async def override_company():
        return company

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_company] = override_company

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_db, company

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_nlp_status_endpoint(api_client):
    client, mock_db, company = api_client
    product = _fake_product(company.id)
    product_id = product.id

    with patch("app.routers.nlp.get_product_by_id", return_value=product), \
         patch("app.routers.nlp.get_nlp_status", return_value={
             "total_users": 10,
             "nlp_processed": 5,
             "nlp_pending": 5,
             "nlp_failed": 0,
             "progress_pct": 50.0,
         }):
        resp = await client.get(f"/api/v1/products/{product_id}/nlp/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_users"] == 10
    assert data["nlp_processed"] == 5
    assert data["progress_pct"] == 50.0
    assert data["product_id"] == str(product_id)


@pytest.mark.asyncio
async def test_nlp_status_product_not_found(api_client):
    client, mock_db, company = api_client
    fake_id = uuid.uuid4()

    with patch("app.routers.nlp.get_product_by_id", return_value=None):
        resp = await client.get(f"/api/v1/products/{fake_id}/nlp/status")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_nlp_trigger_accepted(api_client):
    client, mock_db, company = api_client
    product = _fake_product(company.id, status="discovering")

    with patch("app.routers.nlp.get_product_by_id", return_value=product), \
         patch("app.services.nlp_service.start_nlp_background", new_callable=AsyncMock):
        resp = await client.post(f"/api/v1/products/{product.id}/nlp/trigger")

    assert resp.status_code == 202
    assert resp.json()["status"] == "queued"


@pytest.mark.asyncio
async def test_nlp_trigger_wrong_status(api_client):
    client, mock_db, company = api_client
    product = _fake_product(company.id, status="pending")

    with patch("app.routers.nlp.get_product_by_id", return_value=product):
        resp = await client.post(f"/api/v1/products/{product.id}/nlp/trigger")

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_nlp_trigger_product_not_found(api_client):
    client, mock_db, company = api_client

    with patch("app.routers.nlp.get_product_by_id", return_value=None):
        resp = await client.post(f"/api/v1/products/{uuid.uuid4()}/nlp/trigger")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_user_nlp_features_not_computed(api_client):
    client, mock_db, company = api_client
    product = _fake_product(company.id)
    user_id = uuid.uuid4()

    with patch("app.routers.nlp.get_product_by_id", return_value=product), \
         patch("app.routers.nlp.get_user_nlp_features", return_value=None):
        resp = await client.get(
            f"/api/v1/products/{product.id}/discovery/users/{user_id}/nlp"
        )

    assert resp.status_code == 404
    assert "NLP features not yet computed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_user_nlp_features_returned(api_client):
    client, mock_db, company = api_client
    product = _fake_product(company.id)
    user_id = uuid.uuid4()
    feat_id = uuid.uuid4()

    from datetime import datetime, timezone
    fake_features = MagicMock()
    fake_features.id = feat_id
    fake_features.user_id = user_id
    fake_features.empath_scores = {"technology": 0.8, "achievement": 0.5}
    fake_features.bertopic_topics = []
    fake_features.spacy_entities = []
    fake_features.interest_tags = ["technology", "achievement"]
    fake_features.keyword_frequency = {"python": 3, "learning": 2}
    fake_features.vocabulary_richness = 0.75
    fake_features.avg_sentence_length = 12.5
    fake_features.total_tokens = 120
    fake_features.created_at = datetime.now(timezone.utc)
    fake_features.updated_at = datetime.now(timezone.utc)

    with patch("app.routers.nlp.get_product_by_id", return_value=product), \
         patch("app.routers.nlp.get_user_nlp_features", return_value=fake_features):
        resp = await client.get(
            f"/api/v1/products/{product.id}/discovery/users/{user_id}/nlp"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["interest_tags"] == ["technology", "achievement"]
    assert data["total_tokens"] == 120
