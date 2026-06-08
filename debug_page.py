"""Debug what's actually in the DOM."""
import asyncio, sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
from playwright.async_api import async_playwright

async def debug():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        # Capture console logs
        logs = []
        page.on("console", lambda msg: logs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: logs.append(f"[ERROR] {err}"))

        await page.goto("http://localhost:3000/login")
        await page.wait_for_timeout(5000)  # wait 5s for JS to load

        # Get all text content
        body = await page.locator("body").inner_html()
        print("BODY HTML (first 3000 chars):")
        print(body[:3000])
        print()

        # Get all inputs
        inputs = await page.locator("input").all()
        print(f"Inputs found: {len(inputs)}")
        for i, inp in enumerate(inputs):
            t = await inp.get_attribute("type")
            placeholder = await inp.get_attribute("placeholder")
            print(f"  input[{i}]: type={t}, placeholder={placeholder}")

        # Get all buttons
        buttons = await page.locator("button").all()
        print(f"Buttons found: {len(buttons)}")
        for i, btn in enumerate(buttons):
            txt = await btn.text_content()
            print(f"  button[{i}]: '{txt}'")

        print()
        print("Console logs:")
        for log in logs[:20]:
            print(f"  {log}")

        await page.screenshot(path="verify_screenshots/debug_login.png", full_page=True)
        await browser.close()

asyncio.run(debug())
