# Aurora watch

Monitor the aurora and get push notifications.

# Installation

Install uv
```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Add an .env file with the following variables:
```sh
OPENWEATHER_API_KEY=your_openweather_api_key
OPENAI_API_KEY=your_openai_api_key
FAIRBANKS_LAT=64.8378
FAIRBANKS_LON=-147.7164
YOUTUBE_ID=youtube_id
POKER_FLAT_IMAGE_URL="https://allsky.gi.alaska.edu/PKR/latest-cam.jpg"
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

Run `aurora.py` every 15 min with a cronjob:

```sh
crontab -e
```

and add

```
*/15 * * * * /root/.local/bin/uv run /root/aurora_watch/aurora.py > /root/aurora_watch/aurora_cron.log 2>&1
```
