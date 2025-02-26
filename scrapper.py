import time
import json
import requests
import schedule
import threading
from flask import Flask, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

app = Flask(__name__)

WEBHOOK_URL_WEEKLY = "https://hook.us2.make.com/z8k8m91n3iw25iw129irporc2ao0iapd"

weekly_leaderboard_data = []  # Stores latest weekly leaderboard data

def scrape_weekly_leaderboard():
    global weekly_leaderboard_data
    
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Run in headless mode
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--log-level=3")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        url = "https://kolscan.io/leaderboard"
        driver.get(url)

        # Wait for the leaderboard to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CLASS_NAME, "leaderboard_leaderboardUser__8OZpJ"))
        )
        print("✅ Leaderboard page loaded.")

        # Locate the "Weekly" tab using the correct XPath
        weekly_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "/html/body/div/div/div[2]/div/div/div[1]/div/p[2]"))
        )

        print("🔄 Switching to Weekly tab...")
        weekly_tab.click()
        time.sleep(2)  # Allow UI update

        # Wait for weekly leaderboard data to load
        print("⏳ Waiting for Weekly leaderboard to load...")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "leaderboard_firstPlace__AShOl"))
        )
        print("✅ Weekly leaderboard data detected!")

        # Extract leaderboard data
        players = driver.find_elements(By.CLASS_NAME, "leaderboard_leaderboardUser__8OZpJ")
        print(f"✅ Found {len(players)} players on the Weekly leaderboard.")

        if not players:
            print("⚠️ No leaderboard data found. The page structure might have changed.")
            return

        leaderboard = []
        
        for index, player in enumerate(players, start=1):
            try:
                profile_img = player.find_element(By.TAG_NAME, "img").get_attribute("src")
                profile_url = player.find_element(By.TAG_NAME, "a").get_attribute("href")
                wallet_address = profile_url.split("/account/")[-1] if "/account/" in profile_url else "N/A"

                # Extract Name (Get the SECOND <h1>)
                try:
                    h1_elements = player.find_elements(By.TAG_NAME, "h1")
                    if len(h1_elements) > 1:
                        name = h1_elements[1].text.strip()  # Second <h1> contains the name
                    else:
                        name = f"Rank {index}"
                except Exception:
                    name = f"Rank {index}"  # Fallback

                win_loss = player.find_elements(By.CLASS_NAME, "remove-mobile")
                wins, losses = win_loss[1].text.split("/") if len(win_loss) > 1 else ("0", "0")

                sol_profit_element = player.find_element(By.CLASS_NAME, "leaderboard_totalProfitNum__HzfFO")
                sol_number = sol_profit_element.find_elements(By.TAG_NAME, "h1")[0].text.strip()
                dollar_value = sol_profit_element.find_elements(By.TAG_NAME, "h1")[1].text.strip()

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
        driver.quit()

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
