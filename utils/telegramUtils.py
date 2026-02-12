import config
import time
import requests

from utils.utils import log_event


last_update_id = 0


def get_updates():
    global last_update_id

    # 1️⃣ Check token
    if not config.TELEGRAM_TOKEN:
        log_event("❌ TELEGRAM_TOKEN is not set")
        return []

    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getUpdates?timeout=30&offset={last_update_id + 1}"
    try:
        response = requests.get(url, timeout=35)  # slightly longer than API timeout
        response.raise_for_status()  # raises HTTPError if 4xx/5xx

        data = response.json()

        # 2️⃣ Check if response is valid
        if "ok" not in data or not data["ok"]:
            log_event(f"❌ Telegram API returned not OK: {data}")
            return []

        return data.get("result", [])

    except requests.exceptions.RequestException as e:
        log_event(f"❌ Requests exception: {e}")
        return []
    except ValueError as e:
        log_event(f"❌ Failed to parse JSON response: {e}")
        return []


def send_telegram(text, image_path=None):
    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
        log_event(f"Posting to Telegram")
        requests.post(url, data={'chat_id': config.TELEGRAM_CHAT_ID, 'text': text})

        if image_path:
            url = f"https://api.telegram.org/bot{configTELEGRAM_TOKEN}/sendPhoto"
            with open(image_path, 'rb') as img:
                requests.post(url, files={'photo': img}, data={'chat_id': config.TELEGRAM_CHAT_ID})
            log_event(f"Posted to Telegram")
    except Exception as e:
        log_event(f"⚠️ Telegram error: {e}")

# Seconds to wait between polls when no updates (reduces memory/CPU on limited environments)
TELEGRAM_POLL_IDLE_SECONDS = 90

def poll_telegram():
    global last_update_id
    while True:
        updates = get_updates()
        if not updates:
            time.sleep(TELEGRAM_POLL_IDLE_SECONDS)
            continue

        # Take the last (latest) update
        update = updates[-1]
        last_update_id = update["update_id"]

        message = update.get("message", {})
        text = message.get("text")
        chat_id = message.get("chat", {}).get("id")
        log_event(f"Latest Telegram message: {text}")

        if not text:
            time.sleep(1)
            continue

        # Optional: only allow authorized users
        # if str(chat_id) != str(CHAT_ID):
        #     send_telegram("⛔ Unauthorized")
        #     time.sleep(1)
        #     continue

        # ✅ Handle the command
        response = handle_telegram_command(text)
        send_telegram(response)

        time.sleep(1)


def handle_telegram_command(text):
    text = text.strip().lower()
    log_event(f"Response for telegram: {text}")
    if text in ("/on", "on"):
        if config.TRADING_ENABLED:
            return "ℹ️ Trading already ENABLED"
        config.TRADING_ENABLED = True
        return "✅ Trading ENABLED"

    if text in ("/off", "off"):
        if not config.TRADING_ENABLED:
            return "ℹ️ Trading already DISABLED"
        config.TRADING_ENABLED = False
        return "⛔ Trading DISABLED"

    if text in ("/status", "status"):
        mode = "SIGNALS ONLY" if config.TRADING_SIGNALS_ONLY else "LIVE TRADING"
        state = "ON" if config.TRADING_ENABLED else "OFF"
        return f"📊 Status: {state} | Mode: {mode}"

    return "❓ Use /on /off /status"
