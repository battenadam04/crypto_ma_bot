from utils.exchangeUtils import fetch_balance_and_notify
from utils.telegramUtils import send_telegram


DAILY_LOSS_LIMIT = 0.30  # 30%
loss_triggered = False  # reset manually when ready to resume

def check_daily_loss_limit():
    global start_of_day_balance, loss_triggered

    if loss_triggered:
        print("🚨 Trading disabled due to previous loss trigger.")
        return False

    current_balance = fetch_balance_and_notify()

    if start_of_day_balance is None:
        print("⚠️ No start-of-day balance set, skipping check.")
        return True  # allow trades to continue

    loss_pct = (start_of_day_balance - current_balance) / start_of_day_balance

    if loss_pct >= DAILY_LOSS_LIMIT:
        loss_triggered = True
        send_telegram(
            f"🛑 Trading stopped: Balance down {loss_pct*100:.2f}% since start of day. Investigate before resuming."
        )
        return False

    return True
