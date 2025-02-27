import time
import json
import requests
import schedule
import threading
from flask import Flask, jsonify
from playwright.sync_api import sync_playwright

app = Flask(__name__)

WEBHOOK_URL_WEEKLY = "https://hook.us2.make.com/z8k8m91n3iw25iw129irporc2ao0iapd"

weekly_leaderboard_data = []  # Stores latest weekly leaderboard data

def scrape_weekly_leaderboard():
    global weekly_leaderboard_data

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  # ✅ Fix: Run in headless mode
        page = browser.new_page()

        try:
            url = "https://kolscan.io/leaderboard"
            print("🌍 Navigating to:", url)
            page.goto(url, timeout=60000)
            page.wait_for_load_state("networkidle")
            print("✅ Page loaded.")

            # Force multiple reloads to ensure fresh data
            for i in range(2):  # Reload twice
                print(f"🔄 Reloading leaderboard... Attempt {i+1}")
                page.reload()
                page.wait_for_load_state("networkidle")
                time.sleep(3)  # Small delay
            print("✅ Leaderboard fully refreshed.")

            # Locate and click the "Weekly" tab
            weekly_tab = page.locator("xpath=//p[contains(text(), 'Weekly')]")
            weekly_tab.wait_for(timeout=10000)
            print("🔄 Clicking Weekly tab...")
            weekly_tab.click()
            page.wait_for_timeout(5000)  # Allow UI update

            # Confirm Weekly leaderboard is loaded
            first_rank_selector = ".leaderboard_firstPlace__AShOl"
            print("⏳ Waiting for first-ranked player to appear...")
            page.wait_for_selector(first_rank_selector, timeout=15000)
            print("✅ First-ranked player detected!")

            # Extract leaderboard data
            players = page.locator(".leaderboard_leaderboardUser__8OZpJ").all()
            print(f"✅ Found {len(players)} players on the Weekly leaderboard.")

            if not players:
                print("⚠️ No leaderboard data found. The page structure might have changed.")
                return

            leaderboard = []

            for index, player in enumerate(players, start=1):
                try:
                    # Ensure we ONLY get the profile image, ignoring Twitter/Telegram icons
                    profile_img = player.locator("a div img").nth(0).get_attribute("src")
                    
                    # ✅ Fix: Correct profile URL extraction
                    profile_url_element = player.locator("a").nth(0)  
                    profile_url = profile_url_element.get_attribute("href") if profile_url_element else "N/A"
                    wallet_address = profile_url.split("/account/")[-1] if "/account/" in profile_url else "N/A"

                    # ✅ Fix for Rank 1 Name Extraction
                    if index == 1:
                        name_element = player.locator("h1").nth(0)  # Get first <h1> for rank 1
                    else:
                        name_element = player.locator("h1").nth(1)  # Get second <h1> for others

                    name = name_element.inner_text().strip() if name_element else f"Rank {index}"

                    # Extract Wins / Losses
                    win_loss = player.locator(".remove-mobile").all()
                    wins, losses = win_loss[1].inner_text().split("/") if len(win_loss) > 1 else ("0", "0")

                    # ✅ Fix: Correct SOL Profit & Dollar Value Extraction
                    sol_profit = player.locator(".leaderboard_totalProfitNum__HzfFO h1").all()
                    sol_number = sol_profit[0].inner_text().strip() if len(sol_profit) > 0 else "0"
                    dollar_value = sol_profit[1].inner_text().strip() if len(sol_profit) > 1 else "$0"

                    leaderboard.append({
                        "rank": index,
                        "profile_icon": profile_img,
                        "name": name,
                        "profile_url": profile_url,
                        "wallet_address": wallet_address,
                        "wins": wins.strip(),
                        "losses": losses.strip(),
                        "sol_number": sol_number.strip(),
                        "dollar_value": dollar_value.strip()
                    })

                except Exception as e:
                    print(f"❌ Error extracting weekly data for rank {index}: {e}")

            # Save the scraped data
            weekly_leaderboard_data = leaderboard

            # Send data to webhook
            try:
                response = requests.post(WEBHOOK_URL_WEEKLY, json={"weekly_leaderboard": leaderboard})
                response.raise_for_status()
                print("✅ Weekly data sent successfully:", response.status_code)
            except requests.exceptions.RequestException as e:
                print("❌ Failed to send weekly data:", e)

        finally:
            browser.close()

# Schedule to run every Monday at 12:00 AM
schedule.every().monday.at("00:00").do(scrape_weekly_leaderboard)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

threading.Thread(target=run_scheduler, daemon=True).start()

@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "Kolscan Leaderboard Scraper is running! Use /scrape_weekly to trigger scraping."})

@app.route("/scrape_weekly", methods=["GET"])
def manual_scrape_weekly():
    scrape_weekly_leaderboard()
    return jsonify({"message": "Weekly scraping triggered!", "data": weekly_leaderboard_data})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
