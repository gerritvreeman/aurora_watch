# /// script
# dependencies = [
#   "requests",
#   "astral",
#   "openai",
#   "dotenv",
#   "pytz",
# ]
# ///

import requests
import subprocess
from datetime import datetime, timedelta, timezone
from astral import LocationInfo
from astral.sun import sun
import openai
import base64
import json
import pytz
from dotenv import load_dotenv
import os

load_dotenv()

# ---- CONFIG ----
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FAIRBANKS_LAT = os.getenv("FAIRBANKS_LAT")
FAIRBANKS_LON = os.getenv("FAIRBANKS_LON")
POKER_FLAT_IMAGE_URL = os.getenv("POKER_FLAT_IMAGE_URL")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ---- STEP 1: Check Aurora Forecast ----
def get_aurora_probability():
    url = "https://services.swpc.noaa.gov/json/ovation_aurora_latest.json"
    data = requests.get(url).json()

    # Check a small 3x3 grid around Fairbanks for robustness
    fairbanks_data = [
        point
        for point in data["coordinates"]
        if (211 <= point[0] <= 213) and (64 <= point[1] <= 66)
    ]

    probability = max([cell[2] for cell in fairbanks_data], default=0)
    print(f"Aurora probability for the next 30 min over Fairbanks: {probability}%")
    return probability


# ---- STEP 2: Check if it's dark ----
def is_dark_in_fairbanks():
    location = LocationInfo("Fairbanks", "US", "America/Anchorage", 64.8, -147.7)
    today = datetime.now(pytz.timezone("US/Alaska"))
    today_sun = sun(location.observer, date=today)
    sunrise = today_sun["sunrise"] - timedelta(hours=2)
    sunset = today_sun["sunset"] + timedelta(hours=2)

    print(f"Current time: {today}")
    print(f"Sunrise time-2hrs: {sunrise}")
    print(f"Sunset time+2hrs: {sunset}")

    if sunrise <= today <= sunset:
        return False
    else:
        return True


# ---- STEP 3: Check Weather Conditions ----
def is_clear_weather():
    url = f"http://api.openweathermap.org/data/2.5/weather?lat={FAIRBANKS_LAT}&lon={FAIRBANKS_LON}&appid={OPENWEATHER_API_KEY}&units=metric"
    weather = requests.get(url).json()
    cloud_coverage = weather["clouds"]["all"]
    print(f"Cloud coverage: {cloud_coverage}%")
    return cloud_coverage, cloud_coverage < 100# skip if more than 95% cloud cover


# ---- STEP 4: Fetch Poker Flat Image ----
def fetch_poker_flat_image():
    response = requests.get(POKER_FLAT_IMAGE_URL)
    with open("poker_flat.jpg", "wb") as file:
        file.write(response.content)
    print("Downloaded Poker Flat image.")


# ---- STEP 5: GPT-4 Vision Analysis ----
def analyze_aurora_images(aurora_probability, cloud_cover):
    client = openai.OpenAI(api_key=f"{OPENAI_API_KEY}")

    # Convert images to base64 data URLs
    def encode_image(file_path):
        with open(file_path, "rb") as image_file:
            return f"data:image/jpeg;base64,{base64.b64encode(image_file.read()).decode('utf-8')}"

    poker_flat_data_url = encode_image("/root/poker_flat.jpg")

    prompt = f"""
You are an expert in aurora observation and analysis. You are receiving night-sky images from Fairbanks, Alaska, where aurora activity is being monitored.

**Contextual Information:**
- Aurora forecast probability: {aurora_probability}%
- Cloud cover: {cloud_cover}%

**Please analyze the images and answer the following questions:**
1. Do you see any visible aurora in either or both images? Look for green. Only return "yes" if the aurora is somewhat good (i.e., qualitative intensity is at least moderate, like 2 or above).
2. How would you describe the qualitative intensity? Use a scale from 0 to 10 where 0 is no intensity and 10 is highest intensity.
3. How confident are you in your assessment?
4. How does the current cloud cover affect visibility? Please put more empasis on the image analysis compared to cloud cover percentage.
5. Provide a brief summary combining the images and data into a recommendation for aurora watchers, 15 words or less.

Please return your analysis in the following JSON format, include only json in the response, no markdown delims:
    "aurora_detected": "yes" or "no",
    "qualitative_intensity": number, 0 to 10 with 0 being none and 10 being high,
    "confidence": "Low", "Moderate", or "High",
    "weather_comment": "Brief weather impact comment",
    "analysis_summary": "Brief combined summary"
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an expert aurora observer."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": poker_flat_data_url}},
                ],
            },
        ],
        max_tokens=500,
    )

    analysis_text = response.choices[0].message.content
    print("\nAurora Analysis Report:\n", analysis_text)

    return analysis_text


def send_telegram_alert(message, image_paths=None):
    """Send text message, optionally with one or two images to Telegram."""

    if image_paths and len(image_paths) == 1:
        # Original single photo version
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        with open(image_paths[0], "rb") as photo:
            data = {"chat_id": TELEGRAM_CHAT_ID, "caption": message}
            files = {"photo": photo}
            response = requests.post(url, data=data, files=files)

    elif image_paths and len(image_paths) == 2:
        # Two-photo media group version
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMediaGroup"

        files = {
            "photo0": open(image_paths[0], "rb"),
        }

        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "media": f"""
            [
                {{"type": "photo", "media": "attach://photo0", "caption": "{message}"}},
                {{"type": "photo", "media": "attach://photo1"}}
            ]
            """,
        }

        response = requests.post(url, files=files, data=data)

        for f in files.values():
            f.close()

    else:
        # Text-only version
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        response = requests.post(url, data=data)

    if response.status_code == 200:
        print("✅  Telegram alert sent.")
    else:
        print(f"❌  Failed to send Telegram alert: {response.text}")


def process_analysis_and_send_alert(analysis_text):
    try:
        analysis = json.loads(analysis_text)

        aurora_detected = analysis.get("aurora_detected", "yes").lower()
        summary = analysis.get("analysis_summary", "Aurora detected — check the sky!")

        if aurora_detected == "yes":
            print("Aurora detected — sending Telegram alert.")
            send_telegram_alert(summary, ["/root/poker_flat.jpg"])
        else:
            print("No aurora detected — no alert sent.")
    except json.JSONDecodeError:
        print("❓  Analysis response was not valid JSON — fallback to keyword search.")
        if '"aurora_detected": "yes"' in analysis_text.lower():
            send_telegram_alert("Aurora detected — check the sky!", ["/root/poker_flat.jpg"])
        else:
            print("No aurora detected — no alert sent.")


# ---- MAIN FLOW ----
def main():
    if not is_dark_in_fairbanks():
        print("It's too bright — skipping.")
        return

    cloud_cover, clear = is_clear_weather()
    if not clear:
        print("Too cloudy — skipping.")
        return

    aurora_probability = get_aurora_probability()
    if aurora_probability < 10:
        print("Aurora probability too low — skipping.")
        return

    print("Conditions look good — capturing images.")
    fetch_poker_flat_image()

    analysis = analyze_aurora_images(aurora_probability, cloud_cover)
    process_analysis_and_send_alert(analysis)

if __name__ == "__main__":
    main()
