import time
import json
import requests
import schedule
import threading
from flask import Flask, jsonify
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

app = Flask(__name__)

WEBHOOK_URL_WEEKLY = "https://hook.us2.make.com/z8k8m91n3iw25iw129irporc2ao0iapd"

weekly_leaderboard_data = []  # Stores latest weekly leaderboard data

def click_x_icons_and_get_urls(page):
    """
    From the loaded leaderboard page, clicks each player's X icon,
    captures the popup URL (or same‑tab navigation), and returns a list
    of Twitter/X URLs (or "N/A" if not available).
    """
    x_urls = []
    try:
        # Wait up to 10 seconds for the player containers to appear
        page.wait_for_selector("div.leaderboard_leaderboardUser__8OZpJ", timeout=10000)
    except Exception as e:
        print(f"❌ Timeout waiting for player containers: {e}")
        return ["N/A"]
    
    players_locator = page.locator("div.leaderboard_leaderboardUser__8OZpJ")
    count = players_locator.count()
    print(f"[Playwright] Found {count} player containers.")

    for i in range(count):
        container = players_locator.nth(i)
        x_icon = container.locator("img[src*='Twitter.webp'], img[src*='twitter.png']")
        if x_icon.count() > 0:
            try:
                with page.expect_popup(timeout=3000) as popup_info:
                    x_icon.first.click(force=True)
                popup_page = popup_info.value
                x_url = popup_page.url
                popup_page.close()
                x_urls.append(x_url if "twitter.com" in x_url or "x.com" in x_url else "N/A")
            except Exception as e:
                print(f"[Playwright] Popup attempt failed for container {i}: {e}")
                try:
                    with page.expect_navigation(timeout=3000):
                        x_icon.first.click(force=True)
                    new_url = page.url
                    x_urls.append(new_url if "twitter.com" in new_url or "x.com" in new_url else "N/A")
                    page.go_back()
                except Exception as e:
                    print(f"[Playwright] Navigation fallback failed for container {i}: {e}")
                    x_urls.append("N/A")
        else:
            x_urls.append("N/A")
    return x_urls

def scrape_weekly_leaderboard():
    global weekly_leaderboard_data

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
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

            # --- NEW: Extract X profile URLs using Playwright ---
            print("🔄 Extracting X profile URLs...")
            x_urls = click_x_icons_and_get_urls(page)
            print("✅ Extracted X profile URLs.")

            # Extract leaderboard data (using BeautifulSoup)
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            players = soup.select(".leaderboard_leaderboardUser__8OZpJ")
            print(f"✅ Found {len(players)} players on the Weekly leaderboard.")

            if not players:
                print("⚠️ No leaderboard data found.")
                browser.close()
                return

            leaderboard = []

            for index, player in enumerate(players, start=1):
                try:
                    # Ensure we ONLY get the profile image, ignoring Twitter/Telegram icons
                    profile_img = player.select_one("a div img").get("src")
                    
                    # Correct profile URL extraction
                    profile_url = player.select_one("a").get("href")
                    wallet_address = profile_url.split("/account/")[-1] if "/account/" in profile_url else "N/A"

                    # Fix for Rank 1 Name Extraction: rank 1 uses first h1, others use second
                    if index == 1:
                        name = player.select("h1")[0].text.strip() if len(player.select("h1")) > 0 else f"Rank {index}"
                    else:
                        name = player.select("h1")[1].text.strip() if len(player.select("h1")) > 1 else f"Rank {index}"

                    # Extract Wins / Losses
                    win_loss = [elem.text for elem in player.select(".remove-mobile")]
                    if len(win_loss) > 1 and "/" in win_loss[1]:
                        wins, losses = [x.strip() for x in win_loss[1].split("/")]
                    else:
                        wins, losses = ("0", "0")

                    # Extract SOL profit & Dollar value
                    sol_profit = [elem.text for elem in player.select(".leaderboard_totalProfitNum__HzfFO h1")]
                    sol_number = sol_profit[0].strip() if len(sol_profit) > 0 else "0"
                    dollar_value = sol_profit[1].strip() if len(sol_profit) > 1 else "$0"

                    leaderboard.append({
                        "rank": index,
                        "profile_icon": profile_img,
                        "name": name,
                        "profile_url": profile_url,
                        "wallet_address": wallet_address,
                        "wins": wins,
                        "losses": losses,
                        "sol_number": sol_number,
                        "dollar_value": dollar_value,
                        "x_profile_url": x_urls[index - 1] if index - 1 < len(x_urls) else "N/A"
                    })

                except Exception as e:
                    print(f"❌ Error extracting weekly data for rank {index}: {e}")

            weekly_leaderboard_data = leaderboard

            # Send data to webhook
            try:
                response = requests.post(WEBHOOK_URL_WEEKLY, json={"weekly_leaderboard": leaderboard}, timeout=8)
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
