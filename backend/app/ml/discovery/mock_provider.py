"""
MockDiscoveryProvider — used when Reddit credentials are absent or
MOCK_DISCOVERY=True is set in .env.

Generates realistic fake user profiles and content so the entire
discovery → NLP → OCEAN → Matching pipeline can be tested and demoed
without real Reddit credentials.

The mock data is intentionally varied (different categories, locations,
OCEAN-relevant language) so the downstream pipeline produces
meaningful differentiation.
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone

from app.ml.discovery.base import BaseDiscoveryProvider, ContentItem, RawDiscoveredUser

# ── Static mock user pool ────────────────────────────────────────────────────
# 30 users across 5 psychographic archetypes so the pipeline has enough
# variation to produce realistic Hot / Warm / Cold tier distribution.

_MOCK_USERS: list[dict] = [
    # ── Aesthetic / Design types (high Openness) ──────────────────────────────
    {"u": "design_nerd_chn",    "display": "Priya Sharma",   "city": "Chennai",
     "bio": "Interior designer in Chennai with 6 years of experience. Passionate about sustainable luxury, clean lines, and making spaces tell stories. Always hunting for that perfect statement piece.",
     "karma": 12400, "via": "interiordesign"},
    {"u": "minimal_homes_india", "display": "Riya Kapoor",   "city": "Chennai",
     "bio": "Minimalist home enthusiast. Chennai-based. Scandinavian aesthetics meet Indian warmth. Follow for weekly home inspo and honest product reviews.",
     "karma": 8900, "via": "malelivingspace"},
    {"u": "artstudio_kv",       "display": "Kavitha Rajan",  "city": "Chennai",
     "bio": "Artist and furniture collector based in Chennai, Tamil Nadu. I believe every room deserves a masterpiece. Premium is always worth it.",
     "karma": 5600, "via": "femalelivingspace"},
    {"u": "nordic_spaces_in",   "display": "Meera Krishnan", "city": "Bangalore",
     "bio": "Architect exploring Nordic design principles in Indian homes. 8 years in sustainable residential design. Bangalore based.",
     "karma": 7200, "via": "architecture"},
    {"u": "home_aesthete_mr",   "display": "Manohar Reddy",  "city": "Hyderabad",
     "bio": "Home aesthetics obsessive. Hyderabad. Spend weekends visiting furniture expos. Only buy quality that lasts a decade.",
     "karma": 4300, "via": "HomeDecorating"},

    # ── Luxury / Status types (high Extraversion + low Agreeableness) ─────────
    {"u": "luxlife_arjun",      "display": "Arjun Kapoor",   "city": "Mumbai",
     "bio": "Luxury living redefined. Premium interiors and lifestyle content. Mumbai & Chennai. DM for collaborations. 28k followers on Instagram.",
     "karma": 28300, "via": "luxuryhomes"},
    {"u": "premiumonly_vik",    "display": "Vikram Singh",    "city": "Delhi",
     "bio": "Finance professional in Delhi. I believe in buying the best once rather than cheap things twice. Only premium brands make it into my home.",
     "karma": 9100, "via": "fatFIRE"},
    {"u": "statusroom_nk",      "display": "Nikhil Kumar",   "city": "Mumbai",
     "bio": "Interior stylist to HNI clients across Mumbai. Brand ambassador for luxury home labels. Your home is your personal brand.",
     "karma": 15600, "via": "lifestyleadvice"},
    {"u": "hnindia_rp",         "display": "Rahul Patel",     "city": "Ahmedabad",
     "bio": "Entrepreneur in Ahmedabad. I invest in my home the same way I invest in my business — only what holds or grows in value.",
     "karma": 6800, "via": "india"},
    {"u": "exclusivehome_sm",   "display": "Siddharth Mehta", "city": "Mumbai",
     "bio": "Collections manager. Mumbai. If it's not premium, it doesn't belong in my space. Building a home that reflects real success.",
     "karma": 11200, "via": "luxuryhomes"},

    # ── Comfort / Family types (high Agreeableness + Conscientiousness) ───────
    {"u": "family_nest_kv",     "display": "Kavita Venkat",  "city": "Chennai",
     "bio": "Mom of two making our Chennai home beautiful and durable. Love finding great quality furniture that actually survives kids and cats.",
     "karma": 1800, "via": "Chennai"},
    {"u": "cozy_home_sb",       "display": "Sunita Bhat",     "city": "Pune",
     "bio": "Home maker in Pune. Creating a cozy, family-friendly living space on a sensible budget. Three kids and one very enthusiastic Labrador.",
     "karma": 2300, "via": "Parenting"},
    {"u": "nestbuilder_an",     "display": "Ananya Nair",     "city": "Kochi",
     "bio": "Kerala-based home enthusiast. Extended family living means comfort for all is non-negotiable. Durability and easy-clean are my priorities.",
     "karma": 1500, "via": "Kerala"},
    {"u": "homefamily_rg",      "display": "Ramesh Gupta",    "city": "Jaipur",
     "bio": "Joint family home renovation in Jaipur. 5 members including elderly parents. Comfort and accessibility guide every purchase decision.",
     "karma": 900, "via": "india"},
    {"u": "kidproofhome_mp",    "display": "Meenakshi Pillai","city": "Chennai",
     "bio": "Occupational therapist and mom. Chennai. Everything in our home has to work for both kids and adults. Durability is the only luxury I care about.",
     "karma": 2100, "via": "Chennai"},

    # ── Durability / Quality types (high Conscientiousness) ──────────────────
    {"u": "buyitforlife_sn",    "display": "Suresh Nair",     "city": "Chennai",
     "bio": "Engineer turned homeowner. Chennai. Obsessed with craftsmanship, build quality, and things that last 20 years. r/buyitforlife is my religion.",
     "karma": 3400, "via": "buyitforlife"},
    {"u": "craftfirst_jb",      "display": "Jayesh Bose",     "city": "Kolkata",
     "bio": "Furniture restorer and quality evangelist in Kolkata. If it's not built to outlast me, I'm not interested. Research-heavy buyer.",
     "karma": 4200, "via": "furniture"},
    {"u": "longterm_dk",        "display": "Dinesh Kumar",    "city": "Bangalore",
     "bio": "Software engineer in Bangalore. I buy furniture the way I buy laptops — spec out everything, read every review, buy once. Currently sofa hunting.",
     "karma": 2800, "via": "bangalore"},
    {"u": "heirloom_quality_gv", "display": "Girish Varma",  "city": "Hyderabad",
     "bio": "Hyderabad. Collector of well-made things. I care about joinery, wood grain, and fabric weight. Most furniture today is disposable. Mine isn't.",
     "karma": 1900, "via": "india"},
    {"u": "research_buyer_ak",  "display": "Anil Krishnan",   "city": "Chennai",
     "bio": "Systems architect by day, furniture researcher by weekend. Chennai. Currently 6 weeks into comparing premium sofas. Spreadsheet available on request.",
     "karma": 3100, "via": "Chennai"},

    # ── Modern Design / Trend types (high Openness + Extraversion) ───────────
    {"u": "modernist_ri",       "display": "Rahul Iyer",      "city": "Chennai",
     "bio": "Architect and design purist. Chennai. Minimalism over maximalism always. Writing about modern Indian living spaces and global design trends.",
     "karma": 4600, "via": "architecture"},
    {"u": "designtrend_na",     "display": "Neha Agarwal",    "city": "Delhi",
     "bio": "Interior trends consultant in Delhi. Advise clients on future-proof design choices. Currently obsessed with curved furniture and warm neutrals.",
     "karma": 9800, "via": "interiordesign"},
    {"u": "contemporaryin_sp",  "display": "Sneha Prasad",    "city": "Bangalore",
     "bio": "UX designer by day, home designer by night. Bangalore. Everything I own is intentional. No clutter. No compromise on design.",
     "karma": 5100, "via": "minimalism"},
    {"u": "scandihome_mt",      "display": "Mohan Thakur",    "city": "Mumbai",
     "bio": "Teacher who discovered Scandinavian design 3 years ago and never looked back. Mumbai. Every purchase is carefully considered.",
     "karma": 2700, "via": "Scandinavian"},
    {"u": "architectlife_ps",   "display": "Preethi Suresh",  "city": "Chennai",
     "bio": "Junior architect in Chennai. Passionate about how design shapes behaviour. Currently furnishing my first apartment very deliberately.",
     "karma": 1600, "via": "Chennai"},

    # ── Eco / Sustainable types ───────────────────────────────────────────────
    {"u": "ecoliving_ap",       "display": "Aryan Patel",     "city": "Ahmedabad",
     "bio": "Environmental consultant in Ahmedabad. Every purchase is a vote. I only buy furniture that is sustainable, traceable, and built to last.",
     "karma": 3600, "via": "ZeroWaste"},
    {"u": "greenhouse_cm",      "display": "Chandana Menon",  "city": "Kochi",
     "bio": "Sustainability blogger, Kerala. Certifying my home as near-zero waste. Premium and eco-friendly are not mutually exclusive.",
     "karma": 4100, "via": "Kerala"},
    {"u": "consciousbuy_sa",    "display": "Sumita Acharya",  "city": "Kolkata",
     "bio": "Conscious consumer in Kolkata. Research every major purchase for environmental impact, social responsibility, and build quality.",
     "karma": 2400, "via": "ZeroWaste"},
    {"u": "sustainhome_rv",     "display": "Rohan Verma",     "city": "Pune",
     "bio": "Green architect in Pune. Natural rubber, reclaimed wood, and ethically sourced materials only. Happy to pay premium for sustainability.",
     "karma": 3800, "via": "sustainability"},
    {"u": "plantbased_home_sk", "display": "Shreya Kumari",   "city": "Bangalore",
     "bio": "Vegan lifestyle blogger in Bangalore. My home reflects my values — cruelty-free, sustainable, and honestly beautiful.",
     "karma": 5900, "via": "minimalism"},
]

_POST_POOL: list[dict] = [
    # Interior design / aesthetics
    {"text": "Finally got around to reupholstering the old sofa. Full-grain vegetable-tanned leather from a Chennai tannery. Took 3 weeks but the result is genuinely incredible — the smell alone is worth it.", "score": 847, "type": "post"},
    {"text": "If you're choosing between a budget sofa and saving up for something proper, please save up. I bought cheap once and spent more replacing it twice. The one premium piece I own anchors the entire room.", "score": 612, "type": "comment"},
    {"text": "I judge apartments by their sofa situation. It tells you everything about the owner's priorities and taste. A quality sofa is non-negotiable in any serious living room.", "score": 394, "type": "post"},
    {"text": "My interior design principle: invest in things you touch and sit on every day. Bed, sofa, chair. Everything else can be budget-conscious.", "score": 523, "type": "comment"},
    {"text": "The problem with most Indian furniture stores is they import the aesthetic but not the quality. Looking for locally made pieces that actually match European build standards.", "score": 287, "type": "post"},
    # Family / practical
    {"text": "Kid-proof sofa recommendations? We have two under-5s and a dog. I need fabric that can be wiped down with a damp cloth without disintegrating.", "score": 201, "type": "post"},
    {"text": "Pro tip for parents buying furniture: get performance fabric. Not a sofa — a performance fabric sofa. The difference when juice gets spilled is literally night and day.", "score": 678, "type": "comment"},
    {"text": "Our living room finally works for the whole family. The sectional was the right call — everyone has their spot, including the dog who has claimed the corner permanently.", "score": 156, "type": "post"},
    # Durability / quality research
    {"text": "Six months of research into sofas and here's what I learned: the frame matters more than the cushion fill. Solid wood joints with mortise and tenon construction. Everything else is decoration.", "score": 943, "type": "post"},
    {"text": "The eight-way hand-tied spring system is the benchmark. If a sofa doesn't have it, the cushions will sag in under 3 years regardless of price. Ask about this before buying anything.", "score": 731, "type": "comment"},
    {"text": "I asked a furniture manufacturer to let me watch them build a sofa. Best buying research I've ever done. You learn more in 2 hours than reading 50 reviews.", "score": 445, "type": "post"},
    # Luxury / status
    {"text": "Finally pulled the trigger on the B&B Italia sofa. 8 weeks for delivery from Italy. The moment it arrived I understood why it costs what it costs. Nothing else compares.", "score": 892, "type": "post"},
    {"text": "Premium furniture is an investment that pays back in quality of life every single day. I don't understand why people scrimp on the thing they use 4 hours daily but splurge on a holiday they take once a year.", "score": 567, "type": "comment"},
    {"text": "Flew to Milan for Salone del Mobile. Yes I know how it sounds. No I have no regrets. It completely changed how I see furniture. Some pieces are genuinely art.", "score": 334, "type": "post"},
    # Modern / minimalist
    {"text": "Moved into a new apartment and I'm finally doing it right this time. Everything will be intentional. No impulse buys. No compromises on design. The sofa sets the tone for everything else.", "score": 298, "type": "post"},
    {"text": "Nordic design in an Indian context is actually a perfect pairing. The warm neutrals and natural materials work beautifully with our climate and colour sensibility.", "score": 421, "type": "comment"},
    {"text": "Less is more in every sense. One quality sofa you love beats three budget pieces you tolerate. Currently rotating between three layouts to find the perfect placement.", "score": 189, "type": "post"},
    # Yoga/fitness (for different product category)
    {"text": "6 months into daily yoga practice and the difference in my flexibility and mental clarity is remarkable. The quality of the mat makes a real difference — non-slip surface changed my practice completely.", "score": 512, "type": "post"},
    {"text": "Invested in a proper 6mm natural rubber mat after months on a foam one. The grip difference is not subtle. My practice improved measurably within a week.", "score": 378, "type": "comment"},
    {"text": "Yoga for software engineers: the single best thing I've done for my posture, focus, and work stress. If you're sitting 8 hours a day at a desk, please start.", "score": 634, "type": "post"},
    # Tech/keyboards (for different product category)
    {"text": "Three years on the same mechanical keyboard and I'm still genuinely excited to type on it every morning. Build quality that makes other keyboards feel like toys.", "score": 756, "type": "post"},
    {"text": "Hot-swappable switches changed everything for me. I can now tune the keyboard to exactly my preference. This is what premium should feel like — customisable to the user, not the other way around.", "score": 489, "type": "comment"},
]


class MockDiscoveryProvider(BaseDiscoveryProvider):
    """
    Simulates Reddit discovery for testing and demo purposes.
    Activated automatically when Reddit credentials are absent.
    Returns realistic Indian users with varied psychographic profiles.
    """

    def __init__(self, delay_ms: int = 50) -> None:
        # delay_ms: simulated latency per user (keeps tests fast; 0 for unit tests)
        self._delay_ms = delay_ms

    @property
    def name(self) -> str:
        return "mock"

    @property
    def platform(self) -> str:
        return "mock"

    async def health_check(self) -> dict:
        return {
            "ok": True,
            "provider": self.name,
            "detail": "Mock provider — no external credentials required",
        }

    async def discover_users(
        self,
        keywords: list[str],
        target_city: str | None,
        max_users: int,
        search_config: dict,
    ) -> list[RawDiscoveredUser]:
        """Return up to max_users mock users, filtered loosely by target_city."""
        city_lower = (target_city or "").lower()
        pool = _MOCK_USERS.copy()

        # Loosely prefer city-matched users
        city_matches = [u for u in pool if city_lower and city_lower in u["city"].lower()]
        others = [u for u in pool if u not in city_matches]
        ordered = city_matches + others

        result: list[RawDiscoveredUser] = []
        for raw in ordered[:max_users]:
            if self._delay_ms:
                await asyncio.sleep(self._delay_ms / 1000)

            bio_lower = (raw["bio"] or "").lower()
            city = raw["city"]

            # Location confidence: confirmed if city explicitly in bio
            if city_lower and city_lower in bio_lower:
                conf = "confirmed"
            elif city_lower and city_lower in raw["via"].lower():
                conf = "inferred"
            elif "india" in bio_lower or "indian" in bio_lower:
                conf = "regional"
            else:
                conf = "unknown"

            result.append(RawDiscoveredUser(
                platform="reddit",
                source_provider="mock",
                username=raw["u"],
                display_name=raw["display"],
                bio=raw["bio"],
                location=raw["city"],
                location_confidence=conf,
                follower_count=raw["karma"],
                post_count=None,  # Reddit: not reliable, always None
                profile_url=f"https://reddit.com/u/{raw['u']}",
                discovered_via=raw["via"],
                raw_profile={
                    "karma": raw["karma"],
                    "subreddit": raw["via"],
                    "mock": True,
                },
            ))
        return result

    async def collect_content(
        self,
        user: RawDiscoveredUser,
        max_items: int,
    ) -> list[ContentItem]:
        """Return up to max_items mock content items for a user."""
        items: list[ContentItem] = []

        # Bio is always the first content item if present
        if user.bio:
            items.append(ContentItem(
                content_type="bio",
                content_text=user.bio,
                source_url=user.profile_url,
                engagement=0,
            ))

        # Deterministically pick posts based on username hash for reproducibility
        seed = sum(ord(c) for c in user.username)
        rng = random.Random(seed)
        shuffled = _POST_POOL.copy()
        rng.shuffle(shuffled)

        for post in shuffled[:max_items - len(items)]:
            if self._delay_ms:
                await asyncio.sleep(self._delay_ms / 1000)
            items.append(ContentItem(
                content_type=post["type"],
                content_text=post["text"],
                source_url=f"https://reddit.com/r/mock/comments/{rng.randint(100000, 999999)}",
                engagement=post["score"] + rng.randint(-50, 50),
                posted_at=datetime(2026, rng.randint(1, 5), rng.randint(1, 28),
                                   tzinfo=timezone.utc),
            ))

        return items[:max_items]
