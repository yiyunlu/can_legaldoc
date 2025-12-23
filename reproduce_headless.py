from playwright.sync_api import sync_playwright
import os
import time

def test_headless():
    with sync_playwright() as p:
        user_data_dir = os.path.abspath(".test_profile")
        print(f"Starting browser in HEADLESS mode... (user_data_dir={user_data_dir})")
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=True,
                channel="chrome",
                args=['--disable-blink-features=AutomationControlled']
            )
            print("Successfully launched. Opening a page...")
            page = context.new_page()
            page.goto("https://www.google.com")
            print(f"Page title: {page.title()}")
            time.sleep(5)
            context.close()
            print("Finished.")
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    test_headless()
