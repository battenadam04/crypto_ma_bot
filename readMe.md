# 📘 Crypto Futures Trading Bot

## 🔍 Overview

This is an automated crypto trading bot built for **KuCoin Futures**, written in Python using the `ccxt` library. It combines **moving average crossover** and **range trading** strategies to detect potential long and short signals.

---

## ⚙️ Features

- ✅ Supports **KuCoin Futures** with `isolated` margin mode  
- 📈 Dual-strategy engine:
  - **MA Crossover Strategy** (10/20/50-period)
  - **Range Detection Strategy** (consolidation breakout)
- 🧠 Adaptive strategy switching based on market trend
- 💬 **Telegram Alerts** (for trade entries, wins, and losses)
- 🔐 Risk Management:
  - Take-Profit (TP) and Stop-Loss (SL)
  - Leverage control (default: `10x`)
  - Max open positions enforced
  - Trade block after consecutive losses per pair
- 📊 Backtesting support using historical data
- 🔁 Runs continuously with polling & cooldowns

---

## 🧠 Strategies

### 1. Moving Average (MA) Crossover Strategy

- Uses 10, 20, and 50-period MAs on the **15-minute chart**.
- Conditions:
  - **Long:** MA10 > MA20 > MA50
  - **Short:** MA10 < MA20 < MA50
- Signals are only accepted when price is trending strongly and cleanly crossing above or below these levels.

### 2. Range Trading Strategy

- Activated when no trend is detected on higher timeframes.
- Detects consolidation zones and breakout points.
- Places orders once price breaks above/below recent high/low with confirmation.

---

## 🛡️ Risk Management Rules

- **Leverage:** 10x (configurable)
- **Minimum Trade Check:** Ensures notional value exceeds KuCoin’s precision & min limits.
- **Take-Profit / Stop-Loss:** Placed immediately after order creation.
- **Max Concurrent Positions:** Configurable (default: 3)
- **Per-Pair Loss Tracking:**
  - If a pair has **2 or more consecutive losses**, it is **skipped** temporarily.
- **Precision Checks:** Entry, TP, and SL prices are rounded to KuCoin’s allowed precision.

---

## 🔁 Execution Flow

1. Fetch top USDT futures pairs (e.g., SHIB/USDT, BTC/USDT).
2. For each pair:
   - Skip if already has max losses or incompatible with isolated margin.
   - Apply strategy (MA or Range).
   - If valid signal: place a limit order with TP/SL.
   - Log trade, update internal state.
3. Poll for order fills and trade result.
4. Repeat every `n` minutes.

---

## 🧪 Backtesting

A separate module is provided for simulating historical performance:

- Uses real historical 1m and 15m candles.
- Applies the same MA/range strategy decision tree.
- Logs win/loss, PnL, and strategy success rate.

---

## 🧩 Environment Variables

Set your KuCoin and Telegram credentials in a `.env` file:

```env
KUCOIN_API_KEY=your_kucoin_api_key
KUCOIN_SECRET=your_kucoin_secret
KUCOIN_PASSPHRASE=your_kucoin_passphrase

TELEGRAM_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
```
---

## 📦 Installation

```bash
git clone https://github.com/your-username/kucoin-trading-bot.git
cd kucoin-trading-bot
pip install -r requirements.txt
```

## ⚙️ Configurable Settings

You can adjust the bot's behavior by modifying the `config.py` file or setting environment variables.

### Example Configuration:

```python
LEVERAGE = 10                   # Default leverage for futures positions
MAX_OPEN_POSITIONS = 3         # Max number of open trades at once
MAX_LOSSES_PER_PAIR = 2        # Max losses before pausing trading on a symbol
MIN_TRADE_USDT = 5             # Minimum USDT value for executing a trade
POLLING_INTERVAL = 60          # Bot checks for new signals every 60 seconds
```

---

### 📈 Backtesting

```markdown
## 📈 Backtesting

You can test your strategy using historical data to evaluate performance before live deployment.

### Run Backtest:

```bash
python backtest_combined_strategy.py
