import asyncio
import time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright
from app.config import settings

async def test_lite():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=str(settings.storage_state_file),
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        print("Navigating to", settings.GEMINI_URL)
        await page.goto(settings.GEMINI_URL, timeout=35000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Confirm mode
        picker = await page.wait_for_selector("[data-test-id='bard-mode-menu-button']", timeout=10000)
        curr_text = (await picker.inner_text()).strip()
        print(f"Current active model: '{curr_text}'")

        # Type prompt
        composer = await page.wait_for_selector(".ql-editor, [contenteditable='true']", timeout=10000)
        await composer.click()
        prompt = "Reply with exactly: 'SUCCESS: Gemini 3.5 Flash-Lite is working!'"
        print(f"Typing prompt: {prompt}")
        await page.keyboard.insert_text(prompt)
        await page.wait_for_timeout(500)

        # Send
        send_btn = await page.query_selector("button[aria-label*='Send message' i], button.send-button, [data-test-id='send-button']")
        if send_btn and await send_btn.is_visible():
            print("Clicking Send button...")
            await send_btn.click()
        else:
            print("Pressing Enter to submit...")
            await page.keyboard.press("Enter")

        print("Waiting for response from Gemini Web...")
        response_text = ""
        for i in range(35):
            stop_btn = await page.query_selector("button[aria-label*='Stop' i]")
            is_generating = stop_btn is not None and await stop_btn.is_visible()

            res_els = await page.query_selector_all(".model-response-text, message-content, [data-test-id='model-response-text']")
            if res_els:
                last_el = res_els[-1]
                t = (await last_el.inner_text()).strip()
                if t and not is_generating:
                    response_text = t
                    break
            await page.wait_for_timeout(1000)

        print("\n" + "=" * 60)
        print("REAL GEMINI WEB RESPONSE:")
        print("=" * 60)
        print(response_text)
        print("=" * 60)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_lite())
