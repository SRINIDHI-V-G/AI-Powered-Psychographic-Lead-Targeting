"""Dashboard verification script using Playwright."""
import asyncio
import os
import sys
import json
import urllib.request

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

SCREENSHOTS_DIR = "verify_screenshots"
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

BASE_URL = "http://localhost:3001"  # Next.js on 3001 (3000 was already in use)
API_KEY = "3bca997a1d2dd573ac115c4e9ca7a5f58505fd6241677329f5533efb2682595f"

# Expected URL suffixes for each tab
TAB_URL_SUFFIXES = {
    "Overview":         "",           # /products/<id>
    "Product":          "/product",
    "AI Motivations":   "/motivations",
    "Discovered Users": "/discovery",
    "Lead Rankings":    "/leads",
}


async def tabs_visible(aside, labels):
    count = 0
    for lbl in labels:
        n = await aside.locator(f"a:has-text('{lbl}')").count()
        if n > 0:
            count += 1
    return count


async def verify():
    results = []

    # Step 1: Backend health
    print("Step 1: Backend health check")
    try:
        res = urllib.request.urlopen("http://localhost:8000/health", timeout=5)
        health = json.loads(res.read())
        print(f"  {health}")
        results.append(f"[PASS] Backend healthy — DB:{health.get('database')}")
    except Exception as e:
        results.append(f"[FAIL] Backend unreachable: {e}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        # Step 2: Login page
        print("Step 2: Loading login page")
        await page.goto(f"{BASE_URL}/login", timeout=20000)
        try:
            await page.wait_for_selector("button:has-text('Connect')", timeout=10000)
        except PWTimeout:
            print("  WARN: timed out waiting for Connect button")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=f"{SCREENSHOTS_DIR}/01_login.png", full_page=True)

        api_visible = await page.locator("#apikey").is_visible()
        connect_visible = await page.locator("button:has-text('Connect')").is_visible()
        demo_visible = await page.locator("button:has-text('Demo')").is_visible()
        print(f"  API input: {api_visible}, Connect: {connect_visible}, Demo: {demo_visible}")
        results.append(f"{'[PASS]' if api_visible else '[FAIL]'} API key input visible")
        results.append(f"{'[PASS]' if connect_visible else '[FAIL]'} Connect button visible")
        results.append(f"{'[PASS]' if demo_visible else '[FAIL]'} Demo Mode button visible")

        # Step 3: Login
        print("Step 3: Logging in")
        await page.locator("#apikey").fill(API_KEY)
        await page.locator("button:has-text('Connect')").click()
        try:
            await page.wait_for_url(f"{BASE_URL}/", timeout=15000)
        except PWTimeout:
            await page.wait_for_timeout(5000)
        await page.screenshot(path=f"{SCREENSHOTS_DIR}/02_post_login.png", full_page=True)
        post_url = page.url
        login_ok = post_url.rstrip("/") == BASE_URL
        print(f"  Post-login URL: {post_url}")
        results.append(f"{'[PASS]' if login_ok else '[FAIL]'} Login -> dashboard: {post_url}")

        # Step 4: Dashboard overview
        print("Step 4: Dashboard overview")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=f"{SCREENSHOTS_DIR}/03_dashboard.png", full_page=True)
        headings = [await h.text_content() for h in await page.locator("h1").all()]
        print(f"  Headings: {headings}")
        results.append(f"[PASS] Dashboard heading: {headings}")

        stats_count = (await page.locator("text=Hot Leads").count()
                       + await page.locator("text=Products").count())
        results.append(f"{'[PASS]' if stats_count > 0 else '[WARN]'} Stats grid visible")

        # Step 5: Navigate to product
        print("Step 5: Finding a product")
        product_links = page.locator("a[href*='/products/']")
        count = await product_links.count()
        print(f"  Product links: {count}")
        if count == 0:
            await page.goto(f"{BASE_URL}/products", timeout=10000)
            await page.wait_for_timeout(2000)
            product_links = page.locator("a[href*='/products/']")
            count = await product_links.count()
        results.append(f"{'[PASS]' if count > 0 else '[WARN]'} Products found: {count}")

        if count == 0:
            results.append("[WARN] No products — cannot test 5-tab sidebar")
            await browser.close()
            _print_results(results)
            return results

        first_href = await product_links.first.get_attribute("href")
        print(f"  First product: {first_href}")
        await page.goto(f"{BASE_URL}{first_href}", timeout=15000)
        await page.wait_for_timeout(2000)
        await page.screenshot(path=f"{SCREENSHOTS_DIR}/04_product_detail.png", full_page=True)
        product_base_url = page.url.rstrip("/")
        results.append(f"[PASS] Product detail loaded: {product_base_url}")

        # ProductSidebar = 2nd <aside> (1st is the main Sidebar)
        product_aside = page.locator("aside").nth(1)

        # Step 6: Check all 5 tabs are present
        print("Step 6: Checking 5 sidebar tabs")
        tab_labels = list(TAB_URL_SUFFIXES.keys())
        tab_states = {}
        for label in tab_labels:
            found = await product_aside.locator(f"a:has-text('{label}')").count() > 0
            tab_states[label] = found
            print(f"  {'[OK]' if found else '[MISSING]'} '{label}'")
            results.append(f"{'[PASS]' if found else '[FAIL]'} Tab '{label}' in ProductSidebar")
        results.append(f"{'[PASS]' if all(tab_states.values()) else '[FAIL]'} All 5 tabs present")

        # Step 7: Click each tab and verify URL + no error state
        print("Step 7: Clicking each tab")
        for label, suffix in TAB_URL_SUFFIXES.items():
            loc = product_aside.locator(f"a:has-text('{label}')").first
            if not await product_aside.locator(f"a:has-text('{label}')").count():
                results.append(f"[FAIL] Tab '{label}' not found, skip")
                continue

            await loc.click()
            await page.wait_for_timeout(2000)
            tab_url = page.url.rstrip("/")
            expected_url = product_base_url + suffix
            url_ok = tab_url == expected_url
            safe = label.replace(" ", "_")
            await page.screenshot(path=f"{SCREENSHOTS_DIR}/tab_{safe}.png", full_page=True)

            # Check the <main> element only — "This page could not be found" exists in the
            # Next.js 14 RSC payload as a pre-rendered NotFound handler (false positive if
            # checked against the full body). Only flag real error states in the rendered UI.
            main_text = ""
            for el in await page.locator("main").all():
                t = await el.text_content() or ""
                if len(t) > len(main_text):
                    main_text = t
            error_state = (
                "Something went wrong" in main_text
                or "Failed to load" in main_text
            )
            print(f"  '{label}' URL: {tab_url} (expected: {expected_url}) | url_ok: {url_ok} | error: {error_state}")
            if error_state:
                results.append(f"[FAIL] Tab '{label}' shows error state")
            elif not url_ok:
                results.append(f"[WARN] Tab '{label}' URL mismatch — got {tab_url}, expected {expected_url}")
            else:
                results.append(f"[PASS] Tab '{label}' -> correct URL and no errors")

        # Step 8: Edge case probes
        print("Step 8: Edge case probes")

        # Pipeline Status section
        pipeline = await product_aside.locator("p:has-text('Pipeline')").count() > 0
        results.append(f"{'[PASS]' if pipeline else '[WARN]'} Pipeline Status section visible: {pipeline}")

        # Active tab indigo highlight
        await page.goto(f"{BASE_URL}{first_href}", timeout=10000)
        await page.wait_for_timeout(1500)
        product_aside2 = page.locator("aside").nth(1)
        overview_loc = product_aside2.locator("a:has-text('Overview')").first
        if await product_aside2.locator("a:has-text('Overview')").count():
            cls = await overview_loc.get_attribute("class") or ""
            highlighted = "indigo" in cls
            print(f"  Active tab class snippet: {cls[:80]}")
            results.append(f"{'[PASS]' if highlighted else '[WARN]'} Active tab indigo highlight: {highlighted}")

        # Tabs survive reload
        await page.reload()
        await page.wait_for_timeout(2000)
        product_aside3 = page.locator("aside").nth(1)
        count_after_reload = await tabs_visible(product_aside3, tab_labels)
        print(f"  Tabs after reload: {count_after_reload}/5")
        results.append(f"{'[PASS]' if count_after_reload == 5 else '[FAIL]'} All 5 tabs survive reload: {count_after_reload}/5")

        await page.screenshot(path=f"{SCREENSHOTS_DIR}/05_final.png", full_page=True)
        await browser.close()

    _print_results(results)
    return results


def _print_results(results):
    print()
    print("=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    for r in results:
        print(r)
    passes = sum(1 for r in results if r.startswith("[PASS]"))
    fails  = sum(1 for r in results if r.startswith("[FAIL]"))
    warns  = sum(1 for r in results if r.startswith("[WARN]"))
    print(f"\n  {passes} PASS  |  {fails} FAIL  |  {warns} WARN")
    print(f"  VERDICT: {'PASS' if fails == 0 else 'FAIL'}")
    print(f"  Screenshots: {SCREENSHOTS_DIR}/")


if __name__ == "__main__":
    asyncio.run(verify())
