from utils.exchangeUtils import fetch_balance_and_notify
from utils.telegramUtils import send_telegram
from config import DAILY_LOSS_LIMIT
start_of_day_balance = None
loss_triggered = False  # reset manually when ready to resume

def check_daily_loss_limit():
    global start_of_day_balance, loss_triggered

    if loss_triggered:
        print("🚨 Trading disabled due to previous loss trigger.")
        return False

    current_balance = fetch_balance_and_notify()

    if current_balance is None:
        print("⚠️ Could not fetch current balance, skipping check.")
        return True

    if start_of_day_balance is None:
        start_of_day_balance = current_balance
        print(f"📌 Start-of-day balance initialized to {start_of_day_balance:.2f} USDT.")
        return True

    loss_pct = (start_of_day_balance - current_balance) / start_of_day_balance

    if loss_pct >= DAILY_LOSS_LIMIT:
        loss_triggered = True
        send_telegram(
            f"🛑 Trading stopped: Balance down {loss_pct*100:.2f}% since start of day. Investigate before resuming."
        )
        return False

    return True
