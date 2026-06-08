import asyncio, sys
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv(".env")

DONOR = "bae69788-4352-4d39-ac27-bb99ecc3521b"   # Test Product - motivations_generated
TARGET = "eee20f77-d0d3-48bf-acb9-a4240d7918ef"  # FitTrack Pro v2 - our E2E product

async def main():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:

        # 1. Current product state
        r = await db.execute(text("SELECT name, status, pipeline_step FROM products WHERE id = :id"), {"id": TARGET})
        row = r.fetchone()
        print(f"PRODUCT: {row[0]}  status={row[1]}  step={row[2]}")

        # 2. Check existing motivations on target
        r = await db.execute(text("SELECT COUNT(*) FROM motivation_categories WHERE product_id = :id"), {"id": TARGET})
        mc_count = r.scalar()
        print(f"EXISTING MOTIVATIONS ON TARGET: {mc_count}")

        if mc_count == 0:
            # 3. Copy motivation_categories from donor
            await db.execute(text("""
                INSERT INTO motivation_categories
                    (id, product_id, name, description, is_active, sort_order, created_at, updated_at)
                SELECT gen_random_uuid(), :target, name, description, is_active, sort_order, NOW(), NOW()
                FROM motivation_categories WHERE product_id = :donor
            """), {"target": TARGET, "donor": DONOR})
            await db.commit()

            # 4. Get the new category IDs and donor profile data, copy ocean profiles
            r = await db.execute(text("""
                SELECT new_mc.id, old_mc.id as old_id
                FROM motivation_categories new_mc
                JOIN motivation_categories old_mc ON old_mc.name = new_mc.name
                WHERE new_mc.product_id = :target AND old_mc.product_id = :donor
            """), {"target": TARGET, "donor": DONOR})
            pairs = r.fetchall()

            for new_id, old_id in pairs:
                # get columns that actually exist in motivation_ocean_profiles
                r2 = await db.execute(text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'motivation_ocean_profiles'
                    ORDER BY ordinal_position
                """))
                cols = [row[0] for row in r2.fetchall()]
                print(f"  motivation_ocean_profiles columns: {cols}")

                r3 = await db.execute(text("""
                    SELECT * FROM motivation_ocean_profiles WHERE motivation_category_id = :oid
                """), {"oid": old_id})
                profile = r3.fetchone()
                if profile:
                    col_names = list(profile._mapping.keys())
                    col_values = dict(profile._mapping)
                    col_values["id"] = "gen_random_uuid()"
                    col_values["motivation_category_id"] = str(new_id)
                    col_values.pop("id", None)  # remove old id
                    # Build insert
                    insert_cols = [c for c in col_names if c not in ("id",)]
                    placeholders = []
                    params = {"new_id": str(new_id)}
                    for col in insert_cols:
                        if col == "motivation_category_id":
                            placeholders.append(f":{col}")
                            params[col] = str(new_id)
                        elif col in ("created_at", "updated_at"):
                            placeholders.append("NOW()")
                        else:
                            placeholders.append(f":{col}")
                            params[col] = col_values[col]
                    sql = f"""
                        INSERT INTO motivation_ocean_profiles (id, {', '.join(insert_cols)})
                        VALUES (gen_random_uuid(), {', '.join(placeholders)})
                        ON CONFLICT DO NOTHING
                    """
                    await db.execute(text(sql), params)
            await db.commit()
            print("MOTIVATIONS + OCEAN PROFILES COPIED")
        else:
            print("MOTIVATIONS ALREADY EXIST - skipping copy")

        # 5. Advance product to motivations_generated
        await db.execute(text("""
            UPDATE products
            SET status = 'motivations_generated', pipeline_step = 2,
                error_message = NULL, updated_at = NOW()
            WHERE id = :id
        """), {"id": TARGET})
        await db.commit()

        # 6. Verify final state
        r = await db.execute(text("SELECT status, pipeline_step FROM products WHERE id = :id"), {"id": TARGET})
        row = r.fetchone()
        r2 = await db.execute(text("SELECT COUNT(*) FROM motivation_categories WHERE product_id = :id"), {"id": TARGET})
        mc = r2.scalar()
        r3 = await db.execute(text("""
            SELECT COUNT(*) FROM motivation_ocean_profiles mop
            JOIN motivation_categories mc ON mop.motivation_category_id = mc.id
            WHERE mc.product_id = :id
        """), {"id": TARGET})
        ocean = r3.scalar()
        print(f"FINAL STATE: status={row[0]}  step={row[1]}")
        print(f"MOTIVATION CATEGORIES: {mc}")
        print(f"OCEAN PROFILES: {ocean}")

asyncio.run(main())
