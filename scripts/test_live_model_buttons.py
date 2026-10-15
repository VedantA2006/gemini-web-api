import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright
from app.config import settings

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=str(settings.storage_state_file),
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.goto(settings.GEMINI_URL, timeout=35000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Click the mode picker button
        picker = await page.wait_for_selector("[data-test-id='bard-mode-menu-button']", timeout=10000)
        curr_text = (await picker.inner_text()).strip()
        print(f"Current mode button text: {repr(curr_text)}")

        print("Clicking mode picker...")
        await picker.click()
        await page.wait_for_timeout(1500)

        # Find menu options
        options = await page.query_selector_all("[role='menuitem'], .mat-mdc-menu-item, [role='option'], .mode-item")
        print(f"Found {len(options)} menu options:")
        for idx, opt in enumerate(options):
            txt = (await opt.inner_text()).replace("\n", " -- ").strip()
            aria = await opt.get_attribute("aria-label") or ""
            print(f"  Option [{idx}]: {txt}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
