"""Check what text appears on each tab main content area."""
import asyncio, sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
from playwright.async_api import async_playwright

BASE_URL = "http://localhost:3001"
API_KEY = "3bca997a1d2dd573ac115c4e9ca7a5f58505fd6241677329f5533efb2682595f"
PRODUCT_ID = "424e8c2f-3ccf-41d9-8ee4-2f1a5f121053"

TAB_URLS = {
    "Overview":         f"/products/{PRODUCT_ID}",
    "Product":          f"/products/{PRODUCT_ID}/product",
    "AI Motivations":   f"/products/{PRODUCT_ID}/motivations",
    "Discovered Users": f"/products/{PRODUCT_ID}/discovery",
    "Lead Rankings":    f"/products/{PRODUCT_ID}/leads",
}

async def debug():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        # Login
        await page.goto(f"{BASE_URL}/login", timeout=20000)
        await page.wait_for_selector("button:has-text('Connect')", timeout=10000)
        await page.locator("#apikey").fill(API_KEY)
        await page.locator("button:has-text('Connect')").click()
        await page.wait_for_url(f"{BASE_URL}/", timeout=15000)
        print("Logged in\n")

        for tab, path in TAB_URLS.items():
            await page.goto(f"{BASE_URL}{path}", timeout=15000)
            await page.wait_for_timeout(3000)

            # Get text from the <main> element (actual content, not sidebars)
            main_text = ""
            main_els = await page.locator("main").all()
            for el in main_els:
                t = await el.text_content() or ""
                if len(t) > len(main_text):
                    main_text = t
            clean_main = " ".join(main_text.split())[:500]

            # Check for specific strings
            full_body = await page.locator("body").text_content() or ""
            has_failed = "Failed to load" in full_body
            has_error_state = "Failed to load" in full_body or "Something went wrong" in full_body
            has_404 = "This page could not be found" in full_body
            has_loading = "Loading" in full_body

            print(f"=== {tab} ===")
            print(f"  URL: {page.url}")
            print(f"  'Failed to load' in body: {has_failed}")
            print(f"  '404 page not found' in body: {has_404}")
            print(f"  'Loading' in body: {has_loading}")
            print(f"  Main content: {clean_main[:300] if clean_main else '(empty)'}")
            print()

        await browser.close()

asyncio.run(debug())
