import asyncio
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright
from app.config import settings

async def check():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            storage_state=str(settings.storage_state_file),
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()
        await page.goto("https://gemini.google.com/app", timeout=35000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        print("PAGE URL:", page.url)
        print("PAGE TITLE:", await page.title())

        signin = await page.query_selector("a[href*='accounts.google.com'], button:has-text('Sign in')")
        avatar = await page.query_selector("a[aria-label*='Google Account' i], img[alt*='Google Account' i], button[aria-label*='Google Account' i]")
        print("SIGN-IN BUTTON PRESENT:", signin is not None)
        print("USER AVATAR PRESENT:", avatar is not None)

        picker = await page.query_selector("[data-test-id='bard-mode-menu-button']")
        if picker:
            print("MODE PICKER TEXT:", (await picker.inner_text()).strip())
            await picker.click()
            await page.wait_for_timeout(1000)
            items = await page.query_selector_all("[role='menuitem'], [role='option'], .mat-mdc-menu-item")
            print(f"FOUND {len(items)} MENU ITEMS:")
            for idx, it in enumerate(items):
                t = (await it.inner_text()).replace("\n", " -- ").strip()
                print(f"  [{idx}]: {t}")
        else:
            print("MODE PICKER NOT FOUND")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(check())
