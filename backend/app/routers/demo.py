"""
Demo router — instant full-pipeline simulation for live demos.
No authentication required. All endpoints return realistic mock data instantly.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path

from app.database import get_db
from app.models.product import Product, ProductStatus
from app.schemas.company import CompanyCreate
from app.schemas.product import ProductCreate
from app.crud.company import create_company, get_company_by_email
from app.crud.product import create_product
from app.crud.motivation import (
    create_motivation_category,
    create_ocean_profile,
    delete_motivations_by_product,
)

router = APIRouter(prefix="/demo", tags=["Demo"])

DEMO_EMAIL = "demo@psycholead.ai"

# ── Hardcoded realistic demo data ─────────────────────────────────────────────

MOCK_MOTIVATIONS = [
    {
        "name": "Aesthetic & Interior Design",
        "description": "These buyers purchase primarily for visual appeal and how the sofa elevates their living space. They follow interior design trends, share home decor content, and treat furniture as art.",
        "ocean": {"openness": 8.5, "conscientiousness": 6.0, "extraversion": 6.5, "agreeableness": 6.0, "emotional_stability": 6.5},
        "interest_tags": ["interior design", "home decor", "architecture", "aesthetics", "lifestyle"],
        "search_keywords": ["home decor", "living room inspiration", "sofa aesthetic", "interior design ideas"],
        "hashtags": ["#interiordesign", "#homedecor", "#livingroom", "#aesthetics"],
    },
    {
        "name": "Luxury & Status Signaling",
        "description": "Motivated by social status and prestige, these buyers want their premium sofa to signal success and taste. They invest in high-end brands and prioritize perceived value over utility.",
        "ocean": {"openness": 7.5, "conscientiousness": 5.5, "extraversion": 8.0, "agreeableness": 4.5, "emotional_stability": 7.0},
        "interest_tags": ["luxury lifestyle", "premium brands", "status", "fashion", "high-end living"],
        "search_keywords": ["luxury sofa", "italian leather furniture", "designer sofa", "premium home"],
        "hashtags": ["#luxuryliving", "#premiumfurniture", "#luxurylifestyle", "#highendhomes"],
    },
    {
        "name": "Comfort & Family Living",
        "description": "Practical buyers focused on the whole family's comfort. They prioritize durability, ease of cleaning, and how the sofa serves daily family needs — aesthetics come second.",
        "ocean": {"openness": 5.5, "conscientiousness": 8.0, "extraversion": 4.5, "agreeableness": 8.5, "emotional_stability": 7.5},
        "interest_tags": ["family home", "parenting", "comfort", "practical living", "home life"],
        "search_keywords": ["family sofa", "comfortable seating", "durable sofa for kids", "easy clean"],
        "hashtags": ["#familyhome", "#comfortliving", "#homefamily", "#practicalfurniture"],
    },
    {
        "name": "Long-Term Durability Focus",
        "description": "Research-driven buyers who spend weeks comparing materials, warranties, and craftsmanship. They view the sofa as a long-term investment and want provable quality for their money.",
        "ocean": {"openness": 6.5, "conscientiousness": 9.0, "extraversion": 4.0, "agreeableness": 6.5, "emotional_stability": 8.0},
        "interest_tags": ["quality products", "investment", "craftsmanship", "sustainability", "reviews"],
        "search_keywords": ["best sofa quality", "durable leather sofa", "sofa warranty", "craftsman furniture"],
        "hashtags": ["#qualityfurniture", "#craftmanship", "#sustainableliving", "#bestquality"],
    },
    {
        "name": "Modern Design Appreciation",
        "description": "Trend-conscious buyers who follow contemporary design movements and want their home to reflect cutting-edge tastes. They mix premium pieces with minimalist, Scandinavian aesthetics.",
        "ocean": {"openness": 8.0, "conscientiousness": 6.5, "extraversion": 7.0, "agreeableness": 5.5, "emotional_stability": 7.0},
        "interest_tags": ["modern design", "minimalism", "contemporary", "architecture", "scandinavian"],
        "search_keywords": ["modern sofa", "contemporary furniture", "minimalist living", "nordic furniture"],
        "hashtags": ["#moderndesign", "#minimalist", "#contemporaryfurniture", "#nordicdesign"],
    },
]

MOCK_USERS = [
    {"id": "u1", "rank": 1, "username": "interior_queen_chn", "display_name": "Priya Sharma", "platform": "instagram", "bio": "Interior design enthusiast from Chennai. Transforming spaces into stories. Home Decor Content Creator with 5+ years experience.", "follower_count": 12400, "post_count": 847, "location": "Chennai, Tamil Nadu", "compatibility_score": 0.87, "tier": "hot", "best_motivation": "Aesthetic & Interior Design", "ocean": {"openness": 8.8, "conscientiousness": 6.2, "extraversion": 7.1, "agreeableness": 6.4, "emotional_stability": 6.8}, "personality_match": 0.91, "interest_match": 0.85, "activity_score": 0.88, "confidence_score": 0.82},
    {"id": "u2", "rank": 2, "username": "luxury_homes_india", "display_name": "Arjun Kapoor", "platform": "instagram", "bio": "Luxury living redefined. Premium interiors and lifestyle content. Chennai & Mumbai. DM for collaborations.", "follower_count": 28300, "post_count": 1243, "location": "Chennai", "compatibility_score": 0.84, "tier": "hot", "best_motivation": "Luxury & Status Signaling", "ocean": {"openness": 7.8, "conscientiousness": 5.3, "extraversion": 8.4, "agreeableness": 4.2, "emotional_stability": 7.2}, "personality_match": 0.88, "interest_match": 0.82, "activity_score": 0.92, "confidence_score": 0.79},
    {"id": "u3", "rank": 3, "username": "designstudio_chn", "display_name": "Meera Krishnan", "platform": "reddit", "bio": "Interior designer with 8 years experience. Passionate about sustainable luxury and timeless design. Based in Chennai.", "follower_count": 5600, "post_count": 392, "location": "Chennai", "compatibility_score": 0.81, "tier": "hot", "best_motivation": "Modern Design Appreciation", "ocean": {"openness": 8.3, "conscientiousness": 7.1, "extraversion": 6.2, "agreeableness": 5.8, "emotional_stability": 7.4}, "personality_match": 0.84, "interest_match": 0.80, "activity_score": 0.76, "confidence_score": 0.85},
    {"id": "u4", "rank": 4, "username": "homedecor_namma", "display_name": "Kavitha Rajan", "platform": "instagram", "bio": "Chennai based home stylist. Cozy homes on any budget. Follow for weekly interior inspiration and honest reviews.", "follower_count": 8900, "post_count": 621, "location": "Chennai, TN", "compatibility_score": 0.78, "tier": "hot", "best_motivation": "Aesthetic & Interior Design", "ocean": {"openness": 8.1, "conscientiousness": 6.8, "extraversion": 5.9, "agreeableness": 7.2, "emotional_stability": 6.1}, "personality_match": 0.81, "interest_match": 0.77, "activity_score": 0.74, "confidence_score": 0.78},
    {"id": "u5", "rank": 5, "username": "modernliving_chn", "display_name": "Rahul Iyer", "platform": "twitter", "bio": "Architect and design purist based in Chennai. Minimalism over maximalism every time. Writing about modern spaces.", "follower_count": 3200, "post_count": 1876, "location": "Chennai", "compatibility_score": 0.74, "tier": "warm", "best_motivation": "Modern Design Appreciation", "ocean": {"openness": 8.6, "conscientiousness": 7.4, "extraversion": 5.1, "agreeableness": 5.4, "emotional_stability": 7.8}, "personality_match": 0.77, "interest_match": 0.73, "activity_score": 0.69, "confidence_score": 0.81},
    {"id": "u6", "rank": 6, "username": "family_nest_india", "display_name": "Sunita Venkat", "platform": "reddit", "bio": "Mom of two making our Chennai home beautiful. Love finding great quality furniture that actually lasts.", "follower_count": 1800, "post_count": 243, "location": "Chennai, India", "compatibility_score": 0.69, "tier": "warm", "best_motivation": "Comfort & Family Living", "ocean": {"openness": 5.8, "conscientiousness": 8.2, "extraversion": 4.3, "agreeableness": 8.9, "emotional_stability": 7.6}, "personality_match": 0.71, "interest_match": 0.68, "activity_score": 0.64, "confidence_score": 0.74},
    {"id": "u7", "rank": 7, "username": "craft_quality_ind", "display_name": "Suresh Nair", "platform": "twitter", "bio": "Engineer turned homeowner. Chennai. Obsessed with craftsmanship, build quality, and things that last 20 years.", "follower_count": 2100, "post_count": 934, "location": "Chennai", "compatibility_score": 0.65, "tier": "warm", "best_motivation": "Long-Term Durability Focus", "ocean": {"openness": 6.4, "conscientiousness": 9.2, "extraversion": 3.8, "agreeableness": 6.7, "emotional_stability": 8.3}, "personality_match": 0.67, "interest_match": 0.64, "activity_score": 0.61, "confidence_score": 0.76},
    {"id": "u8", "rank": 8, "username": "chennai_homestyle", "display_name": "Deepa Murthy", "platform": "instagram", "bio": "Sharing my home journey from empty apartment to dream home. Chennai interior enthusiast and newbie decorator.", "follower_count": 4300, "post_count": 287, "location": "Chennai", "compatibility_score": 0.58, "tier": "warm", "best_motivation": "Aesthetic & Interior Design", "ocean": {"openness": 7.2, "conscientiousness": 5.9, "extraversion": 6.8, "agreeableness": 7.4, "emotional_stability": 5.8}, "personality_match": 0.60, "interest_match": 0.57, "activity_score": 0.55, "confidence_score": 0.68},
    {"id": "u9", "rank": 9, "username": "premiumbuyer_chn", "display_name": "Vikram Anand", "platform": "reddit", "bio": "Finance professional in Chennai. Strong believer in buying the best once rather than cheap twice.", "follower_count": 890, "post_count": 412, "location": "Chennai, TN", "compatibility_score": 0.51, "tier": "cold", "best_motivation": "Long-Term Durability Focus", "ocean": {"openness": 6.1, "conscientiousness": 8.7, "extraversion": 4.6, "agreeableness": 5.9, "emotional_stability": 8.1}, "personality_match": 0.53, "interest_match": 0.50, "activity_score": 0.47, "confidence_score": 0.71},
    {"id": "u10", "rank": 10, "username": "lifestyle_bliss_chn", "display_name": "Ananya Bose", "platform": "instagram", "bio": "Lifestyle blogger covering fashion, food, and home in Chennai. Collab inquiries welcome.", "follower_count": 15600, "post_count": 1923, "location": "Chennai", "compatibility_score": 0.44, "tier": "cold", "best_motivation": "Comfort & Family Living", "ocean": {"openness": 7.0, "conscientiousness": 5.1, "extraversion": 8.2, "agreeableness": 7.1, "emotional_stability": 6.3}, "personality_match": 0.46, "interest_match": 0.43, "activity_score": 0.71, "confidence_score": 0.58},
]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/setup", summary="One-click demo: create company + product + run full pipeline")
async def setup_demo(db: AsyncSession = Depends(get_db)):
    # Reuse existing demo company if it exists
    company = await get_company_by_email(db, DEMO_EMAIL)
    if not company:
        company = await create_company(db, CompanyCreate(
            name="Comfort Furniture India",
            email=DEMO_EMAIL,
            industry="Furniture & Home Decor",
        ))

    # Create product
    product = await create_product(
        db,
        ProductCreate(
            name="Premium Sofa",
            description=(
                "Handcrafted 3-seater premium sofa with full-grain Italian leather "
                "and solid oak frame. The centrepiece for any luxury living room in Chennai."
            ),
            category="Furniture",
            subcategory="Sofas",
            price_range="premium",
            target_location="Chennai, Tamil Nadu",
            target_city="Chennai",
            keywords=["sofa", "furniture", "interior design", "home decor", "leather"],
        ),
        company.id,
    )

    # Instantly create mock motivations in DB
    await _seed_mock_motivations(db, product.id)

    # Mark pipeline complete
    product.status = ProductStatus.completed
    product.pipeline_step = 9
    await db.commit()

    return {
        "company_id": str(company.id),
        "api_key": company.api_key,
        "product_id": str(product.id),
        "product_name": product.name,
        "target_location": product.target_location,
        "status": "demo_ready",
    }


@router.post("/{product_id}/instant", summary="Instantly run full pipeline for existing product")
async def run_instant_pipeline(product_id: UUID, db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    await _seed_mock_motivations(db, product.id)
    product.status = ProductStatus.completed
    product.pipeline_step = 9
    await db.commit()

    return {"status": "completed", "pipeline_step": 9}


@router.get("/{product_id}/users", summary="Get mock discovered users")
async def get_demo_users(product_id: str):
    return {
        "product_id": product_id,
        "total_discovered": 847,
        "total_analyzed": 823,
        "displayed": len(MOCK_USERS),
        "users": MOCK_USERS,
    }


@router.get("/{product_id}/leads", summary="Get mock ranked leads")
async def get_demo_leads(product_id: str):
    return {
        "product_id": product_id,
        "total": len(MOCK_USERS),
        "hot_count": sum(1 for u in MOCK_USERS if u["tier"] == "hot"),
        "warm_count": sum(1 for u in MOCK_USERS if u["tier"] == "warm"),
        "cold_count": sum(1 for u in MOCK_USERS if u["tier"] == "cold"),
        "avg_compatibility": round(sum(u["compatibility_score"] for u in MOCK_USERS) / len(MOCK_USERS), 2),
        "leads": MOCK_USERS,
    }


@router.get("/{product_id}/stats", summary="Get mock pipeline stats")
async def get_demo_stats(product_id: str):
    return {
        "pipeline_steps_completed": 9,
        "users_discovered": 847,
        "content_collected": 15234,
        "ocean_scored": 823,
        "leads_ranked": 10,
        "hot_leads": 4,
        "warm_leads": 4,
        "cold_leads": 2,
        "avg_compatibility_score": 0.69,
        "top_motivation": "Aesthetic & Interior Design",
        "discovery_sources": {"instagram": 412, "reddit": 248, "twitter": 187},
        "processing_time_seconds": 847,
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _seed_mock_motivations(db, product_id) -> None:
    await delete_motivations_by_product(db, product_id)
    for i, cat in enumerate(MOCK_MOTIVATIONS):
        mc = await create_motivation_category(
            db,
            product_id=product_id,
            name=cat["name"],
            description=cat["description"],
            sort_order=i,
        )
        await create_ocean_profile(
            db,
            motivation_category_id=mc.id,
            ocean_data={
                **cat["ocean"],
                "interest_tags": cat["interest_tags"],
                "search_keywords": cat["search_keywords"],
                "hashtags": cat["hashtags"],
            },
        )
    await db.commit()
