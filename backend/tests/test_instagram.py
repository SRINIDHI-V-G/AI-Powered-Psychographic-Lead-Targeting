"""
Instagram provider unit tests.

All tests use mocked instagrapi — no real Instagram credentials required,
no internet access required, no Instagram availability required.
Tests are deterministic and fully reproducible.

Coverage:
  Config
    - instagram_credentials_configured() helper
    - use_mock_discovery() accounts for Instagram credentials

  Provider registration
    - InstagramProvider raises without credentials
    - Orchestrator includes InstagramProvider when credentials are configured
    - Orchestrator excludes InstagramProvider when credentials are absent
    - Instagram-only mode (no Reddit/YouTube) does NOT fall back to mock

  Discovery
    - keywords_to_hashtags conversion logic
    - discover_users returns RawDiscoveredUser list
    - poster extraction (username, bio, platform, source_provider)
    - commenter extraction
    - poster/commenter merge → discovery_method = "both"
    - private profiles are skipped
    - failed hashtag search is handled gracefully
    - location inference (confirmed, regional, unknown)
    - profile fields populated correctly

  Content collection
    - bio included as content_type='bio'
    - post captions included as content_type='post'
    - comment texts included as content_type='comment'
    - additional posts fetched when primary content is sparse
    - collect_content returns at most max_items

  Authentication
    - session load attempted before fresh login
    - session saved after successful login
    - LoginRequired triggers re-auth (once)
    - PleaseWaitFewMinutes triggers sleep + retry
    - stale session (LoginRequired on first use) → fresh login
    - ChallengeRequired → RuntimeError with instructions

  Health check
    - returns ok=True when account_info succeeds
    - returns ok=False when account_info raises

Run:
  cd backend && pytest tests/test_instagram.py -v
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Mock instagrapi before importing the provider ─────────────────────────────
# Ensures tests work even when instagrapi is not installed in the test
# environment, and prevents any real Instagram network calls.

class _LoginRequired(Exception):
    pass

class _PleaseWaitFewMinutes(Exception):
    pass

class _ChallengeRequired(Exception):
    pass

class _PrivateError(Exception):
    pass

class _UserNotFound(Exception):
    pass

class _MediaNotFound(Exception):
    pass

_mock_exceptions = MagicMock()
_mock_exceptions.LoginRequired = _LoginRequired
_mock_exceptions.PleaseWaitFewMinutes = _PleaseWaitFewMinutes
_mock_exceptions.ChallengeRequired = _ChallengeRequired
_mock_exceptions.PrivateError = _PrivateError
_mock_exceptions.UserNotFound = _UserNotFound
_mock_exceptions.MediaNotFound = _MediaNotFound

_mock_instagrapi = MagicMock()
_mock_instagrapi.exceptions = _mock_exceptions

# Register mock module — if instagrapi is installed the real module is replaced
# for this test session only.
sys.modules["instagrapi"] = _mock_instagrapi
sys.modules["instagrapi.exceptions"] = _mock_exceptions


# ── Mock data helpers ─────────────────────────────────────────────────────────
# Instagram PKs are always numeric in production; use numeric strings so that
# int(user_pk) calls in the provider work correctly.

def _user_short(pk: str = "1001", username: str = "testuser", full_name: str = ""):
    u = MagicMock()
    u.pk = pk
    u.username = username
    u.full_name = full_name or username.replace("_", " ").title()
    return u


def _media(
    pk: str = "10001",
    user_pk: str = "1001",
    username: str = "testuser",
    caption: str = "Great premium sofa for Chennai living!",
    code: str = "ABCDE",
    like_count: int = 120,
):
    m = MagicMock()
    m.pk = pk
    m.user = _user_short(pk=user_pk, username=username)
    m.caption_text = caption
    m.code = code
    m.like_count = like_count
    m.taken_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    return m


def _comment(
    pk: str = "20001",
    user_pk: str = "1002",
    username: str = "commenter",
    text: str = "Love this sofa for my Chennai apartment!",
    like_count: int = 5,
):
    c = MagicMock()
    c.pk = pk
    c.user = _user_short(pk=user_pk, username=username)
    c.text = text
    c.like_count = like_count
    c.created_at_utc = datetime(2026, 5, 2, tzinfo=timezone.utc)
    return c


def _user_info(
    pk: str = "1001",
    username: str = "testuser",
    bio: str = "Interior designer in Chennai",
    is_private: bool = False,
    follower_count: int = 2400,
    following_count: int = 800,
    media_count: int = 87,
    full_name: str = "",
):
    u = MagicMock()
    u.pk = pk
    u.username = username
    u.full_name = full_name or username.replace("_", " ").title()
    u.biography = bio
    u.is_private = is_private
    u.follower_count = follower_count
    u.following_count = following_count
    u.media_count = media_count
    return u


# ── Provider fixture ──────────────────────────────────────────────────────────

def _make_mock_client():
    """Create a realistic mock of instagrapi.Client."""
    client = MagicMock()
    client.delay_range = [1, 3]
    client.login.return_value = None
    client.dump_settings.return_value = None
    client.load_settings.return_value = {}
    client.set_settings.return_value = None
    account = MagicMock()
    account.username = "test_ig_account"
    account.pk = "999"
    client.account_info.return_value = account
    return client


@pytest.fixture
def mock_client():
    return _make_mock_client()


@pytest.fixture
def provider(mock_client):
    """InstagramProvider with all external dependencies mocked."""
    _mock_instagrapi.Client.return_value = mock_client

    with patch("app.ml.discovery.instagram_provider.settings") as mock_settings:
        mock_settings.instagram_credentials_configured.return_value = True
        mock_settings.INSTAGRAM_USERNAME = "test_account"
        mock_settings.INSTAGRAM_PASSWORD = "test_pass"
        mock_settings.INSTAGRAM_SESSION_ID = ""
        mock_settings.INSTAGRAM_SESSION_FILE = "/tmp/test_ig_session.json"
        mock_settings.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
        mock_settings.INSTAGRAM_MAX_COMMENTS_PER_POST = 10

        with patch("os.path.exists", return_value=False):
            from app.ml.discovery.instagram_provider import InstagramProvider
            prov = InstagramProvider()

    # Ensure the real exception classes (defined above) are used by _api_call
    prov._LoginRequired = _LoginRequired
    prov._PleaseWaitFewMinutes = _PleaseWaitFewMinutes
    prov._ChallengeRequired = _ChallengeRequired
    return prov


# ══════════════════════════════════════════════════════════════════════════════
# 1. CONFIG
# ══════════════════════════════════════════════════════════════════════════════

class TestInstagramConfig:

    def test_credentials_configured_false_by_default(self):
        from app.config import Settings
        s = Settings(DATABASE_URL="postgresql://x/y")
        assert s.instagram_credentials_configured() is False

    def test_credentials_configured_true_when_both_set(self):
        from app.config import Settings
        s = Settings(
            DATABASE_URL="postgresql://x/y",
            INSTAGRAM_USERNAME="myaccount",
            INSTAGRAM_PASSWORD="mypassword",
        )
        assert s.instagram_credentials_configured() is True

    def test_credentials_configured_false_when_only_username(self):
        from app.config import Settings
        s = Settings(DATABASE_URL="postgresql://x/y", INSTAGRAM_USERNAME="myaccount")
        assert s.instagram_credentials_configured() is False

    def test_use_mock_discovery_false_when_instagram_configured(self):
        from app.config import Settings
        s = Settings(
            DATABASE_URL="postgresql://x/y",
            INSTAGRAM_USERNAME="myaccount",
            INSTAGRAM_PASSWORD="mypassword",
        )
        assert s.use_mock_discovery() is False

    def test_use_mock_discovery_true_when_no_credentials(self):
        from app.config import Settings
        s = Settings(DATABASE_URL="postgresql://x/y")
        assert s.use_mock_discovery() is True

    def test_session_file_default(self):
        from app.config import Settings
        s = Settings(DATABASE_URL="postgresql://x/y")
        assert s.INSTAGRAM_SESSION_FILE == "instagram_session.json"

    def test_max_posts_default(self):
        from app.config import Settings
        s = Settings(DATABASE_URL="postgresql://x/y")
        assert s.INSTAGRAM_MAX_POSTS_PER_HASHTAG == 20

    def test_max_comments_default(self):
        from app.config import Settings
        s = Settings(DATABASE_URL="postgresql://x/y")
        assert s.INSTAGRAM_MAX_COMMENTS_PER_POST == 30


# ══════════════════════════════════════════════════════════════════════════════
# 2. PROVIDER REGISTRATION & INITIALISATION
# ══════════════════════════════════════════════════════════════════════════════

class TestInstagramProviderInit:

    def test_raises_without_credentials(self):
        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.instagram_credentials_configured.return_value = False
            from app.ml.discovery.instagram_provider import InstagramProvider
            with pytest.raises(RuntimeError, match="Instagram credentials"):
                InstagramProvider()

    def test_provider_name_is_instagram(self, provider):
        assert provider.name == "instagram"

    def test_provider_platform_is_instagram(self, provider):
        assert provider.platform == "instagram"

    def test_supported_categories_is_wildcard(self, provider):
        assert provider.supported_categories == ["*"]

    def test_supported_regions_is_wildcard(self, provider):
        assert provider.supported_regions == ["*"]

    def test_login_called_on_init(self, mock_client):
        _mock_instagrapi.Client.return_value = mock_client
        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.instagram_credentials_configured.return_value = True
            s.INSTAGRAM_USERNAME = "test_account"
            s.INSTAGRAM_PASSWORD = "test_pass"
            s.INSTAGRAM_SESSION_ID = ""
            s.INSTAGRAM_SESSION_FILE = "/tmp/test.json"
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 10
            with patch("os.path.exists", return_value=False):
                from app.ml.discovery.instagram_provider import InstagramProvider
                InstagramProvider()
        mock_client.login.assert_called_once_with("test_account", "test_pass")

    def test_session_saved_after_login(self, mock_client):
        _mock_instagrapi.Client.return_value = mock_client
        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.instagram_credentials_configured.return_value = True
            s.INSTAGRAM_USERNAME = "test_account"
            s.INSTAGRAM_PASSWORD = "test_pass"
            s.INSTAGRAM_SESSION_ID = ""
            s.INSTAGRAM_SESSION_FILE = "/tmp/test.json"
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 10
            with patch("os.path.exists", return_value=False):
                from app.ml.discovery.instagram_provider import InstagramProvider
                InstagramProvider()
        mock_client.dump_settings.assert_called_once_with("/tmp/test.json")

    def test_delay_range_set(self, provider, mock_client):
        assert mock_client.delay_range == [1, 3]


# ══════════════════════════════════════════════════════════════════════════════
# 3. KEYWORD → HASHTAG CONVERSION
# ══════════════════════════════════════════════════════════════════════════════

class TestKeywordsToHashtags:

    def _convert(self, keywords):
        from app.ml.discovery.instagram_provider import _keywords_to_hashtags
        return _keywords_to_hashtags(keywords)

    def test_single_word_keyword(self):
        assert "sofa" in self._convert(["sofa"])

    def test_multi_word_produces_compound(self):
        assert "luxurysofa" in self._convert(["luxury sofa"])

    def test_multi_word_produces_individual_words(self):
        result = self._convert(["luxury sofa"])
        assert "luxury" in result
        assert "sofa" in result

    def test_compound_precedes_individual_words(self):
        result = self._convert(["interior design"])
        assert result.index("interiordesign") < result.index("interior")

    def test_deduplication(self):
        result = self._convert(["luxury sofa", "luxury furniture"])
        assert result.count("luxury") == 1

    def test_special_chars_stripped(self):
        result = self._convert(["premium #sofa!"])
        assert "premiumsofa" in result

    def test_short_words_excluded(self):
        result = self._convert(["for the home"])
        assert "for" not in result
        assert "the" not in result

    def test_max_30_hashtags(self):
        keywords = [f"keyword{i}" for i in range(50)]
        assert len(self._convert(keywords)) <= 30

    def test_empty_input(self):
        assert self._convert([]) == []

    def test_keywords_lowercased(self):
        result = self._convert(["Luxury Sofa"])
        assert "luxurysofa" in result
        assert "LuxurySofa" not in result


# ══════════════════════════════════════════════════════════════════════════════
# 4. LOCATION INFERENCE
# ══════════════════════════════════════════════════════════════════════════════

class TestLocationInference:

    def _infer(self, bio, target_city, extra=""):
        from app.ml.discovery.instagram_provider import _infer_location
        return _infer_location(bio, target_city, extra)

    def test_confirmed_when_city_in_bio(self):
        loc, conf = self._infer("Interior designer in Chennai", "Chennai")
        assert conf == "confirmed"
        assert loc == "Chennai"

    def test_confirmed_via_city_alias(self):
        loc, conf = self._infer("Based in Madras, TN", "Chennai")
        assert conf == "confirmed"

    def test_confirmed_via_extra_text(self):
        loc, conf = self._infer("Design lover", "Chennai", extra="chennai homes")
        assert conf == "confirmed"

    def test_regional_when_india_in_bio(self):
        loc, conf = self._infer("Indian home decor enthusiast", "Chennai")
        assert conf == "regional"
        assert loc == "India"

    def test_unknown_when_no_signal(self):
        # "design" contains "desi" as a substring but NOT as a whole word
        loc, conf = self._infer("I love design", "Chennai")
        assert conf == "unknown"
        assert loc is None

    def test_desi_as_whole_word_triggers_regional(self):
        loc, conf = self._infer("Proud desi homeowner", "Chennai")
        assert conf == "regional"

    def test_no_target_city_falls_to_regional_on_india_signal(self):
        loc, conf = self._infer("Proud Indian designer", None)
        assert conf == "regional"

    def test_bangalore_alias(self):
        loc, conf = self._infer("Bengaluru-based architect", "Bangalore")
        assert conf == "confirmed"

    def test_unknown_when_empty_bio(self):
        loc, conf = self._infer("", "Chennai")
        assert conf == "unknown"


# ══════════════════════════════════════════════════════════════════════════════
# 5. DISCOVER USERS
# ══════════════════════════════════════════════════════════════════════════════

class TestDiscoverUsers:
    """
    All mock PKs use numeric strings (e.g. "1001") so that int(user_pk) works
    in the provider's user_info call.

    Strategy mapping:
      Strategy 1 — search_users(keyword)  → discovery_method = "search"
      Strategy 2 — seed account comments  → discovery_method = "commenter"
      Both strategies match same user     → discovery_method = "both"
      Strategy 3 — expansion              → post_captions + commenter users
    """

    @pytest.mark.asyncio
    async def test_returns_raw_discovered_users(self, provider, mock_client):
        from app.ml.discovery.base import RawDiscoveredUser

        search_result = _user_short("1001", "priya_designs", "Priya Designs")
        profile1 = _user_info("1001", "priya_designs", bio="Interior designer in Chennai")
        mock_client.search_users_v1.return_value = [search_result]
        mock_client.user_medias.return_value = []
        mock_client.media_comments.return_value = []
        mock_client.user_info.return_value = profile1

        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 10
            with patch("time.sleep"):
                with patch.dict("os.environ", {"INSTAGRAM_SEED_ACCOUNTS": ""}):
                    result = await provider.discover_users(
                        keywords=["luxury sofa"], target_city="Chennai",
                        max_users=10, search_config={},
                    )

        assert len(result) >= 1
        assert isinstance(result[0], RawDiscoveredUser)
        assert result[0].platform == "instagram"
        assert result[0].source_provider == "instagram"

    @pytest.mark.asyncio
    async def test_search_discovery_method(self, provider, mock_client):
        search_result = _user_short("1001", "priya_designs")
        profile1 = _user_info("1001", "priya_designs")
        mock_client.search_users_v1.return_value = [search_result]
        mock_client.user_medias.return_value = []
        mock_client.media_comments.return_value = []
        mock_client.user_info.return_value = profile1

        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 10
            with patch("time.sleep"):
                with patch.dict("os.environ", {"INSTAGRAM_SEED_ACCOUNTS": ""}):
                    result = await provider.discover_users(
                        keywords=["sofa"], target_city=None, max_users=5, search_config={}
                    )

        user = next(u for u in result if u.username == "priya_designs")
        assert user.raw_profile["discovery_method"] == "search"

    @pytest.mark.asyncio
    async def test_commenter_discovery_method(self, provider, mock_client):
        seed_info = _user_info("9999", "furniture_brand")
        media1 = _media("10001", "9999", "furniture_brand")
        comment1 = _comment("20001", "1002", "commenter_user")
        commenter_profile = _user_info("1002", "commenter_user", bio="Chennai design lover")

        mock_client.search_users_v1.return_value = []
        mock_client.user_info_by_username.return_value = seed_info
        mock_client.user_medias.return_value = [media1]
        mock_client.media_comments.return_value = [comment1]
        mock_client.user_info.return_value = commenter_profile

        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 10
            with patch("time.sleep"):
                with patch.dict("os.environ", {"INSTAGRAM_SEED_ACCOUNTS": ""}):
                    result = await provider.discover_users(
                        keywords=["sofa"], target_city="Chennai", max_users=10,
                        search_config={"seed_accounts": ["furniture_brand"]},
                    )

        assert len(result) >= 1
        commenter = next((u for u in result if u.username == "commenter_user"), None)
        assert commenter is not None
        assert commenter.raw_profile["discovery_method"] == "commenter"

    @pytest.mark.asyncio
    async def test_search_commenter_merge(self, provider, mock_client):
        """User found via search AND as commenter on seed account → discovery_method='both'."""
        search_result = _user_short("1001", "dual_user")
        seed_info = _user_info("9999", "furniture_brand")
        media1 = _media("10001", "9999", "furniture_brand")
        comment_on_seed = _comment("20001", "1001", "dual_user", "I love this furniture!")
        dual_profile = _user_info("1001", "dual_user")

        mock_client.search_users_v1.return_value = [search_result]
        mock_client.user_info_by_username.return_value = seed_info
        # user_medias for seed account (strategy 2) returns media1;
        # user_medias for dual_user (strategy 3) returns [] since method becomes "both"
        mock_client.user_medias.return_value = [media1]
        mock_client.media_comments.return_value = [comment_on_seed]
        mock_client.user_info.return_value = dual_profile

        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 10
            with patch("time.sleep"):
                with patch.dict("os.environ", {"INSTAGRAM_SEED_ACCOUNTS": ""}):
                    result = await provider.discover_users(
                        keywords=["sofa"], target_city=None, max_users=10,
                        search_config={"seed_accounts": ["furniture_brand"]},
                    )

        dual = next(u for u in result if u.username == "dual_user")
        assert dual.raw_profile["discovery_method"] == "both"

    @pytest.mark.asyncio
    async def test_private_profiles_skipped(self, provider, mock_client):
        search_result = _user_short("1001", "private_user")
        private_profile = _user_info("1001", "private_user", is_private=True)
        mock_client.search_users_v1.return_value = [search_result]
        mock_client.user_medias.return_value = []
        mock_client.media_comments.return_value = []
        mock_client.user_info.return_value = private_profile

        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 10
            with patch("time.sleep"):
                with patch.dict("os.environ", {"INSTAGRAM_SEED_ACCOUNTS": ""}):
                    result = await provider.discover_users(
                        keywords=["sofa"], target_city=None, max_users=10, search_config={}
                    )

        assert not any(u.username == "private_user" for u in result)

    @pytest.mark.asyncio
    async def test_failed_search_skipped_gracefully(self, provider, mock_client):
        mock_client.search_users_v1.side_effect = Exception("rate limit")

        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 10
            with patch("time.sleep"):
                with patch.dict("os.environ", {"INSTAGRAM_SEED_ACCOUNTS": ""}):
                    result = await provider.discover_users(
                        keywords=["sofa"], target_city=None, max_users=10, search_config={}
                    )

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_max_users_respected(self, provider, mock_client):
        users = [_user_short(f"{2000+i}", f"user{i}") for i in range(10)]
        mock_client.search_users_v1.return_value = users
        mock_client.user_medias.return_value = []
        mock_client.media_comments.return_value = []
        mock_client.user_info.side_effect = lambda pk: _user_info(str(pk), f"user{pk}")

        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 20
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 0
            with patch("time.sleep"):
                with patch.dict("os.environ", {"INSTAGRAM_SEED_ACCOUNTS": ""}):
                    result = await provider.discover_users(
                        keywords=["sofa"], target_city=None, max_users=3, search_config={}
                    )

        assert len(result) <= 3

    @pytest.mark.asyncio
    async def test_location_confirmed_from_bio(self, provider, mock_client):
        search_result = _user_short("1001", "priya_designs")
        profile1 = _user_info("1001", "priya_designs", bio="Interior designer in Chennai.")
        mock_client.search_users_v1.return_value = [search_result]
        mock_client.user_medias.return_value = []
        mock_client.media_comments.return_value = []
        mock_client.user_info.return_value = profile1

        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 10
            with patch("time.sleep"):
                with patch.dict("os.environ", {"INSTAGRAM_SEED_ACCOUNTS": ""}):
                    result = await provider.discover_users(
                        keywords=["luxury sofa"], target_city="Chennai",
                        max_users=10, search_config={},
                    )

        user = next(u for u in result if u.username == "priya_designs")
        assert user.location_confidence == "confirmed"
        assert user.location == "Chennai"

    @pytest.mark.asyncio
    async def test_profile_fields_populated(self, provider, mock_client):
        search_result = _user_short("1001", "priya_designs")
        profile1 = _user_info(
            "1001", "priya_designs",
            bio="Chennai based",
            follower_count=3500,
            media_count=120,
        )
        mock_client.search_users_v1.return_value = [search_result]
        mock_client.user_medias.return_value = []
        mock_client.media_comments.return_value = []
        mock_client.user_info.return_value = profile1

        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 10
            with patch("time.sleep"):
                with patch.dict("os.environ", {"INSTAGRAM_SEED_ACCOUNTS": ""}):
                    result = await provider.discover_users(
                        keywords=["sofa"], target_city=None, max_users=5, search_config={}
                    )

        user = result[0]
        assert user.follower_count == 3500
        assert user.post_count == 120
        assert "instagram.com" in user.profile_url
        assert "priya_designs" in user.profile_url

    @pytest.mark.asyncio
    async def test_post_captions_stored_in_raw_profile(self, provider, mock_client):
        # Caption is stored in Strategy 3 (profile expansion from search result).
        caption = "Absolutely loving this premium Italian leather sofa in my Chennai home!"
        search_result = _user_short("1001", "priya_designs")
        media1 = _media("10001", "1001", "priya_designs", caption=caption)
        profile1 = _user_info("1001", "priya_designs")
        mock_client.search_users_v1.return_value = [search_result]
        mock_client.user_medias.return_value = [media1]
        mock_client.media_comments.return_value = []
        mock_client.user_info.return_value = profile1

        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 10
            with patch("time.sleep"):
                with patch.dict("os.environ", {"INSTAGRAM_SEED_ACCOUNTS": ""}):
                    result = await provider.discover_users(
                        keywords=["sofa"], target_city=None, max_users=5, search_config={}
                    )

        assert caption in result[0].raw_profile["post_captions"]

    @pytest.mark.asyncio
    async def test_comment_texts_stored_in_raw_profile(self, provider, mock_client):
        # Comment texts are stored in Strategy 3 (expansion: commenters on search users' posts).
        comment_text = "This is exactly the sofa I was looking for in Chennai!"
        search_result = _user_short("1001", "poster_user")
        media1 = _media("10001", "1001", "poster_user")
        comment1 = _comment("20001", "1002", "commenter_user", text=comment_text)
        mock_client.search_users_v1.return_value = [search_result]
        mock_client.user_medias.return_value = [media1]
        mock_client.media_comments.return_value = [comment1]
        mock_client.user_info.side_effect = lambda pk: (
            _user_info("1001", "poster_user") if str(pk) == "1001"
            else _user_info("1002", "commenter_user")
        )

        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 10
            with patch("time.sleep"):
                with patch.dict("os.environ", {"INSTAGRAM_SEED_ACCOUNTS": ""}):
                    result = await provider.discover_users(
                        keywords=["sofa"], target_city=None, max_users=10, search_config={}
                    )

        commenter = next(u for u in result if u.username == "commenter_user")
        assert comment_text in commenter.raw_profile["comment_texts"]


# ══════════════════════════════════════════════════════════════════════════════
# 6. CONTENT COLLECTION
# ══════════════════════════════════════════════════════════════════════════════

class TestCollectContent:

    def _make_user(
        self,
        username: str = "priya_designs",
        pk: str = "1001",
        bio: str | None = "Chennai interior designer",
        captions: list | None = None,
        comments: list | None = None,
        method: str = "poster",
    ):
        from app.ml.discovery.base import RawDiscoveredUser
        return RawDiscoveredUser(
            platform="instagram",
            source_provider="instagram",
            platform_user_id=pk,
            username=username,
            bio=bio,
            profile_url=f"https://www.instagram.com/{username}/",
            raw_profile={
                "pk": pk,
                "discovery_method": method,
                "post_captions": captions or [],
                "comment_texts": comments or [],
                "hashtags_seen": ["luxurysofa"],
            },
        )

    @pytest.mark.asyncio
    async def test_bio_included(self, provider, mock_client):
        user = self._make_user(bio="Interior designer in Chennai")
        mock_client.user_medias.return_value = []

        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 10
            items = await provider.collect_content(user, max_items=10)

        bio_items = [i for i in items if i.content_type == "bio"]
        assert len(bio_items) == 1
        assert bio_items[0].content_text == "Interior designer in Chennai"

    @pytest.mark.asyncio
    async def test_post_captions_included(self, provider, mock_client):
        captions = ["Love this luxury sofa!", "Chennai interiors are the best!"]
        user = self._make_user(captions=captions)
        mock_client.user_medias.return_value = []

        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 10
            items = await provider.collect_content(user, max_items=10)

        post_items = [i for i in items if i.content_type == "post"]
        assert len(post_items) == 2

    @pytest.mark.asyncio
    async def test_comment_texts_included(self, provider, mock_client):
        comments = ["This sofa is perfect for Chennai weather!", "Beautiful design"]
        user = self._make_user(comments=comments, method="commenter")
        mock_client.user_medias.return_value = []

        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 10
            items = await provider.collect_content(user, max_items=10)

        comment_items = [i for i in items if i.content_type == "comment"]
        assert len(comment_items) == 2

    @pytest.mark.asyncio
    async def test_respects_max_items(self, provider, mock_client):
        captions = [f"Caption {i} about luxury sofas in Chennai " for i in range(20)]
        user = self._make_user(bio="Bio text", captions=captions)
        mock_client.user_medias.return_value = []

        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 10
            items = await provider.collect_content(user, max_items=5)

        assert len(items) <= 5

    @pytest.mark.asyncio
    async def test_fetches_additional_posts_when_sparse(self, provider, mock_client):
        """When primary content is sparse, user_medias() is called for extra posts."""
        # pk must be numeric so int(pk) works inside _collect_content_sync
        user = self._make_user(bio=None, captions=[], comments=[], pk="1001")
        extra_caption = "More sofa content for my living room in Chennai!"
        extra_media = _media("10099", "1001", "priya_designs", caption=extra_caption)
        mock_client.user_medias.return_value = [extra_media]

        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 10
            items = await provider.collect_content(user, max_items=5)

        mock_client.user_medias.assert_called_once()
        post_items = [i for i in items if i.content_type == "post"]
        assert len(post_items) >= 1
        assert any(extra_caption in i.content_text for i in post_items)

    @pytest.mark.asyncio
    async def test_skips_additional_fetch_when_content_sufficient(self, provider, mock_client):
        """user_medias() should NOT be called when primary content is already sufficient."""
        captions = [f"Sofa caption {i} for Chennai living room here" for i in range(8)]
        user = self._make_user(bio="Bio text", captions=captions)

        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 10
            await provider.collect_content(user, max_items=5)

        mock_client.user_medias.assert_not_called()

    @pytest.mark.asyncio
    async def test_additional_fetch_failure_handled_gracefully(self, provider, mock_client):
        user = self._make_user(bio=None, captions=[], comments=[], pk="1001")
        mock_client.user_medias.side_effect = Exception("API error")

        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 10
            items = await provider.collect_content(user, max_items=5)

        assert isinstance(items, list)

    @pytest.mark.asyncio
    async def test_content_items_have_correct_types(self, provider, mock_client):
        from app.ml.discovery.base import ContentItem
        user = self._make_user(
            bio="Chennai designer",
            captions=["Luxury sofa caption in Chennai here"],
            comments=["Great product this is!"],
        )
        mock_client.user_medias.return_value = []

        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 10
            items = await provider.collect_content(user, max_items=10)

        for item in items:
            assert isinstance(item, ContentItem)
            assert item.content_type in ("bio", "post", "comment")
            assert len(item.content_text) > 0


# ══════════════════════════════════════════════════════════════════════════════
# 7. AUTHENTICATION & SESSION MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

class TestSessionManagement:

    def _build_provider(self, mock_client, session_exists: bool = False):
        _mock_instagrapi.Client.return_value = mock_client
        with patch("app.ml.discovery.instagram_provider.settings") as s:
            s.instagram_credentials_configured.return_value = True
            s.INSTAGRAM_USERNAME = "test_account"
            s.INSTAGRAM_PASSWORD = "test_pass"
            s.INSTAGRAM_SESSION_ID = ""
            s.INSTAGRAM_SESSION_FILE = "/tmp/test.json"
            s.INSTAGRAM_MAX_POSTS_PER_HASHTAG = 5
            s.INSTAGRAM_MAX_COMMENTS_PER_POST = 10
            with patch("os.path.exists", return_value=session_exists):
                from app.ml.discovery.instagram_provider import InstagramProvider
                prov = InstagramProvider()
        prov._LoginRequired = _LoginRequired
        prov._PleaseWaitFewMinutes = _PleaseWaitFewMinutes
        prov._ChallengeRequired = _ChallengeRequired
        return prov

    def test_session_loaded_when_file_exists(self):
        mock_client = _make_mock_client()
        self._build_provider(mock_client, session_exists=True)
        mock_client.load_settings.assert_called_once_with("/tmp/test.json")

    def test_no_session_load_when_file_absent(self):
        mock_client = _make_mock_client()
        self._build_provider(mock_client, session_exists=False)
        mock_client.load_settings.assert_not_called()

    def test_stale_session_triggers_fresh_login(self):
        """LoginRequired after loading session → clear settings + fresh login."""
        mock_client = _make_mock_client()
        # First login raises LoginRequired (stale session), second succeeds
        mock_client.login.side_effect = [_LoginRequired("stale"), None]

        self._build_provider(mock_client, session_exists=True)

        # set_settings({}) must be called to clear the stale session
        mock_client.set_settings.assert_called_with({})
        # login called twice: first with stale cookies, then fresh
        assert mock_client.login.call_count == 2

    def test_login_required_mid_session_triggers_reauth(self, provider, mock_client):
        """_api_call re-authenticates when LoginRequired is raised mid-session."""
        call_count = [0]

        def _fn():
            call_count[0] += 1
            if call_count[0] == 1:
                raise _LoginRequired("session expired")
            return MagicMock(username="test_account", pk="999")

        mock_client.login.reset_mock()
        mock_client.set_settings.reset_mock()
        provider._api_call(_fn)

        assert mock_client.login.called

    def test_please_wait_triggers_sleep_and_retry(self, provider, mock_client):
        call_count = [0]

        def _fn():
            call_count[0] += 1
            if call_count[0] == 1:
                raise _PleaseWaitFewMinutes("slow down")
            return "ok"

        with patch("time.sleep") as mock_sleep:
            result = provider._api_call(_fn)

        mock_sleep.assert_called_once_with(65)
        assert result == "ok"

    def test_challenge_required_raises_runtime_error(self, provider, mock_client):
        mock_client.login.side_effect = _ChallengeRequired("verify identity")
        mock_client.set_settings.return_value = None
        provider._session_id = ""

        with pytest.raises(RuntimeError, match="challenge verification"):
            provider._reauth()


# ══════════════════════════════════════════════════════════════════════════════
# 8. HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════════════

class TestHealthCheck:

    @pytest.mark.asyncio
    async def test_health_check_ok(self, provider, mock_client):
        account = MagicMock()
        account.username = "test_ig_account"
        account.pk = "999"
        mock_client.account_info.return_value = account

        result = await provider.health_check()

        assert result["ok"] is True
        assert result["provider"] == "instagram"
        assert "test_ig_account" in result["detail"]

    @pytest.mark.asyncio
    async def test_health_check_failure(self, provider, mock_client):
        mock_client.account_info.side_effect = Exception("network error")

        result = await provider.health_check()

        assert result["ok"] is False
        assert result["provider"] == "instagram"
        assert "network error" in result["detail"]


# ══════════════════════════════════════════════════════════════════════════════
# 9. ORCHESTRATOR INTEGRATION
# ══════════════════════════════════════════════════════════════════════════════

class TestOrchestratorIntegration:

    def test_registry_empty_when_no_credentials(self):
        with patch("app.ml.discovery.orchestrator.settings") as s:
            s.MOCK_DISCOVERY = False
            s.reddit_credentials_configured.return_value = False
            s.youtube_credentials_configured.return_value = False
            s.instagram_credentials_configured.return_value = False
            from app.ml.discovery.orchestrator import _build_provider_registry
            assert _build_provider_registry() == []

    def test_registry_empty_when_mock_discovery_forced(self):
        with patch("app.ml.discovery.orchestrator.settings") as s:
            s.MOCK_DISCOVERY = True
            s.reddit_credentials_configured.return_value = True
            s.youtube_credentials_configured.return_value = True
            s.instagram_credentials_configured.return_value = True
            from app.ml.discovery.orchestrator import _build_provider_registry
            assert _build_provider_registry() == []

    def test_instagram_only_mode_does_not_fall_back_to_mock(self):
        """
        When only Instagram credentials are configured (no Reddit/YouTube),
        the registry is built (not short-circuited) and InstagramProvider is returned.
        This validates the fix to the old buggy early-return condition.
        """
        mock_ig_instance = MagicMock()
        mock_ig_class = MagicMock(return_value=mock_ig_instance)

        with patch("app.ml.discovery.orchestrator.settings") as s:
            s.MOCK_DISCOVERY = False
            s.reddit_credentials_configured.return_value = False
            s.youtube_credentials_configured.return_value = False
            s.instagram_credentials_configured.return_value = True

            with patch.dict(
                "sys.modules",
                {
                    "app.ml.discovery.instagram_provider": MagicMock(
                        InstagramProvider=mock_ig_class
                    )
                },
            ):
                from app.ml.discovery.orchestrator import _build_provider_registry
                registry = _build_provider_registry()

        mock_ig_class.assert_called_once()
        assert len(registry) == 1
        assert registry[0] is mock_ig_instance

    def test_instagram_not_added_when_credentials_absent(self):
        with patch("app.ml.discovery.orchestrator.settings") as s:
            s.MOCK_DISCOVERY = False
            s.reddit_credentials_configured.return_value = True
            s.youtube_credentials_configured.return_value = False
            s.instagram_credentials_configured.return_value = False

            mock_reddit = MagicMock()
            with patch.dict(
                "sys.modules",
                {"app.ml.discovery.reddit_provider": MagicMock(RedditProvider=MagicMock(return_value=mock_reddit))},
            ):
                from app.ml.discovery.orchestrator import _build_provider_registry
                registry = _build_provider_registry()

        # Only Reddit in the registry
        assert len(registry) == 1

    def test_provider_interface(self, provider):
        """Provider exposes the correct name and platform."""
        assert provider.name == "instagram"
        assert provider.platform == "instagram"
