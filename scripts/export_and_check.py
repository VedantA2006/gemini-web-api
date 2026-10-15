import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright
from app.config import settings

async def main():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(settings.browser_profile_path),
            headless=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(settings.GEMINI_URL, timeout=35000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Check mode button
        picker = await page.wait_for_selector("[data-test-id='bard-mode-menu-button']", timeout=10000)
        curr_text = (await picker.inner_text()).strip()
        print(f"Persistent context mode button: '{curr_text}'")

        # Save the live storage_state.json right now from this context!
        await context.storage_state(path=str(settings.storage_state_file))
        print(f"Exported live storage state to: {settings.storage_state_file}")

        # Check options
        await picker.click()
        await page.wait_for_timeout(1000)
        options = await page.query_selector_all("[role='menuitem'], .mat-mdc-menu-item, [role='option']")
        for idx, opt in enumerate(options):
            txt = (await opt.inner_text()).replace("\n", " -- ").strip()
            print(f"  Option [{idx}]: {txt}")

        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
