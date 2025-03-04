# /// script
# dependencies = [
#   "requests",
#   "yt-dlp",
#   "astral",
#   "openai",
#   "dotenv",
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
from dotenv import load_dotenv
import os

load_dotenv()

# ---- CONFIG ----
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FAIRBANKS_LAT = os.getenv("FAIRBANKS_LAT")
FAIRBANKS_LON = os.getenv("FAIRBANKS_LON")
YOUTUBE_ID = os.getenv("YOUTUBE_ID")
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
    print(f"Current aurora probability over Fairbanks: {probability}%")
    return probability


# ---- STEP 2: Check if it's dark ----
def is_dark_in_fairbanks():
    location = LocationInfo("Fairbanks", "US", "America/Anchorage", 64.8, -147.7)

    now_utc = datetime.now(timezone.utc)

    # Get today and yesterday in UTC
    today = now_utc.date()
    yesterday = today - timedelta(days=1)

    # Get sun events for today and yesterday
    today_sun = sun(location.observer, date=today)
    yesterday_sun = sun(location.observer, date=yesterday)

    # Get the relevant sunset (yesterday evening) and sunrise (this morning)
    sunrise_utc = today_sun["sunrise"]
    sunset_utc = yesterday_sun["sunset"]

    print(f"Yesterday's Sunset (UTC): {sunset_utc}")
    print(f"Today's Sunrise (UTC): {sunrise_utc}")
    print(f"Current time (UTC): {now_utc}")

    # It's dark if we're after sunset and before sunrise
    if sunset_utc <= now_utc <= sunrise_utc:
        return True
    else:
        return False


# ---- STEP 3: Check Weather Conditions ----
def is_clear_weather():
    url = f"http://api.openweathermap.org/data/2.5/weather?lat={FAIRBANKS_LAT}&lon={FAIRBANKS_LON}&appid={OPENWEATHER_API_KEY}&units=metric"
    weather = requests.get(url).json()
    cloud_coverage = weather["clouds"]["all"]
    print(f"Cloud coverage: {cloud_coverage}%")
    return cloud_coverage, cloud_coverage < 75  # skip if more than 75% cloud cover


# ---- STEP 4: Fetch Poker Flat Image ----
def fetch_poker_flat_image():
    response = requests.get(POKER_FLAT_IMAGE_URL)
    with open("poker_flat.jpg", "wb") as file:
        file.write(response.content)
    print("Downloaded Poker Flat image.")


# ---- STEP 5: Fetch YouTube Live Frame ----
def fetch_youtube_frame():
    yt_dlp_command = ["yt-dlp", "-g", f"https://www.youtube.com/watch?v={YOUTUBE_ID}"]
    result = subprocess.run(yt_dlp_command, capture_output=True, text=True, check=True)
    video_url = result.stdout.strip().split("\n")[0]

    ffmpeg_command = ["ffmpeg", "-y", "-i", video_url, "-vframes", "1", "last.jpg"]
    subprocess.run(ffmpeg_command, check=True)
    print("Downloaded YouTube livestream frame.")


# ---- STEP 6: GPT-4 Vision Analysis ----
def analyze_aurora_images(aurora_probability, cloud_cover):
    client = openai.OpenAI(api_key=f"{OPENAI_API_KEY}")

    # Convert images to base64 data URLs
    def encode_image(file_path):
        with open(file_path, "rb") as image_file:
            return f"data:image/jpeg;base64,{base64.b64encode(image_file.read()).decode('utf-8')}"

    poker_flat_data_url = encode_image("poker_flat.jpg")
    youtube_data_url = encode_image("last.jpg")

    prompt = f"""
You are an expert in aurora observation and analysis. You are receiving two night-sky images from Fairbanks, Alaska, where aurora activity is being monitored.

**Contextual Information:**
- Aurora forecast probability: {aurora_probability}%
- Cloud cover: {cloud_cover}%

**Please analyze both images and answer the following questions:**
1. Do you see any visible aurora in either or both images?
2. How would you describe the qualitative intensity? (None, Low, Moderate, High)
3. How confident are you in your assessment?
4. How does the current cloud cover affect visibility?
5. Provide a brief summary combining the images and data into a recommendation for aurora watchers.

Please return your analysis in the following JSON format, include only json in the response, no markdown delims:
    "aurora_detected": "yes" or "no",
    "qualitative_intensity": "None", "Low", "Moderate", or "High",
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
                    {"type": "image_url", "image_url": {"url": youtube_data_url}},
                ],
            },
        ],
        max_tokens=500,
    )

    analysis_text = response.choices[0].message.content
    print("\nAurora Analysis Report:\n", analysis_text)

    return analysis_text


def send_telegram_alert(message, image_path=None):
    """Send text message + optional image to Telegram."""
    if image_path:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        with open(image_path, "rb") as photo:
            data = {"chat_id": TELEGRAM_CHAT_ID, "caption": message}
            files = {"photo": photo}
            response = requests.post(url, data=data, files=files)
    else:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        response = requests.post(url, data=data)

    if response.status_code == 200:
        print("✅ Telegram alert sent.")
    else:
        print(f"❌ Failed to send Telegram alert: {response.text}")


def process_analysis_and_send_alert(analysis_text):
    try:
        analysis = json.loads(analysis_text)

        aurora_detected = analysis.get("aurora_detected", "yes").lower()
        summary = analysis.get("analysis_summary", "Aurora detected — check the sky!")

        if aurora_detected == "yes":
            print("Aurora detected — sending Telegram alert.")
            send_telegram_alert(summary, "last.jpg")
        else:
            print("No aurora detected — no alert sent.")
    except json.JSONDecodeError:
        print("❓ Analysis response was not valid JSON — fallback to keyword search.")
        if '"aurora_detected": "no"' in analysis_text.lower():
            send_telegram_alert("Aurora detected — check the sky!", "last.jpg")
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
    if aurora_probability < 12:
        print("Aurora probability too low — skipping.")
        return

    print("Conditions look good — capturing images.")
    fetch_poker_flat_image()
    fetch_youtube_frame()

    analysis = analyze_aurora_images(aurora_probability, cloud_cover)
    process_analysis_and_send_alert(analysis)

    # Optionally, write analysis to a file for history
    with open("aurora_analysis.txt", "w") as f:
        f.write(analysis)


if __name__ == "__main__":
    main()
