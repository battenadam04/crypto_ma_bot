# Crypto MA Signal Bot

Signals-only crypto alerts via Telegram. Scans exchange market data, scores MA / range setups, and sends indicative entry / TP / SL ideas. **No live orders.**

> Live trading (order placement, balances, positions) is preserved on git tag **`v1.0.0-live-trading`**. This line (`v2.0.0-signals-only` and later) is productized around alerts.

---

## What it does

- Polls OHLCV on a chosen venue (Phemex perps by default; also Binance margin symbols / KuCoin)
- Detects **trend** (MA alignment + HTF confirmation) and **range** (RSI + support/resistance) setups
- Ranks candidates by confirmed signal vs speculative limit-idea, strategy type, and backtest win rate
- Caps noise with **per-symbol cooldown** and **max alerts per cycle**
- Pushes to Telegram with reference price + indicative TP/SL + optional limit-entry hint
- Exposes a small Telegram command menu for status, pairs, backtest digest, timeframe, night pause

---

## Quick start

```bash
cp .env.example .env
# set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python strategies/simulate_trades.py   # optional: refresh last_backtest.json
python bot.py
```

In Telegram: `/on` to start scanning, `/help` for the menu.

---

## Controlling signal volume

Bursts happen when many pairs satisfy the same market condition in one 5m cycle. Controls (env):

| Variable | Default | Effect |
|---|---|---|
| `SIGNAL_COOLDOWN_SEC` | `3600` | Same symbol+direction will not re-alert within this window |
| `MAX_SIGNALS_PER_CYCLE` | `3` | After ranking, only the top N alerts are sent |
| `ENABLE_LIMIT_IDEA_FALLBACK` | `false` | Speculative LIM ideas near S/R — noisy; keep off for a cleaner product |
| `MAIN_LOOP_INTERVAL_SEC` | `300` | Scan cadence |

Ranking order: confirmed `SIG` > speculative `LIM`, then trend > range, then backtest win rate.

---

## Telegram menu (kept vs removed)

**Kept (product-useful):**

| Command | Why |
|---|---|
| `/on` `/off` | Pause / resume alerts without restarting the process |
| `/status` | Health, timeframe, alert caps |
| `/pairs` | Watchlist + backtest win rates — trust signal |
| `/signals` | Today’s alerts + outcome check |
| `/backtest` | Edge proof for the current pair set |
| `/timeframe` | Operator tweak without redeploy |
| `/night` | Quiet hours to cut API churn overnight |
| `/config` `/help` | Transparency / onboarding |

**Removed in signals-only:** `/balance`, `/positions`, `/pnl` (account/trading). Restore from tag `v1.0.0-live-trading` if needed.

---

## Versions

| Tag | Purpose |
|---|---|
| `v1.0.0-live-trading` | Full bot with exchange order placement, balances, TP/SL orders |
| `v2.0.0-signals-only` | Public market data + Telegram signals only |

Restore live trading code:

```bash
git checkout v1.0.0-live-trading
```

---

# Marketing & distribution guide

## Positioning

Sell **decision support**, not a money printer. Pitch:

- *“Curated multi-pair crypto setups with indicative risk levels, delivered as they form.”*
- Emphasize backtested pair filter, cooldown/ranking (signal hygiene), and that you never take custody of funds.

Avoid promising returns. Jurisdiction and advertising rules for financial tip services are strict in many countries — use disclaimers; consider legal advice before charging.

## Who buys this

1. **Manual discretionary traders** who want a second screen of ideas on phone
2. **Small prop / hobby desks** that want a shared Telegram channel of setups
3. **Newsletter / Discord communities** that want an automated feed they can white-label

Not a fit as “fully automated profit bot” — that market is overcrowded and mistrusted, and this codebase no longer places trades.

## Where to market

| Channel | Fit | Notes |
|---|---|---|
| **Telegram** (channel + bot) | Primary delivery | Free/paid invite links; Crypto Bot catalogues; pin EOD stats |
| **Discord** | Strong upsell | Mirror alerts via webhook later; communities pay for roles |
| **Twitter/X + Threads** | Acquisition | Post anonymized signal cards + weekly hit rate (prove process) |
| **Reddit / TradingView ideas** | Awareness | Soft CTA to waitlist; careful with sub rules |
| **Gumroad / Lemon Squeezy** | Checkout | Sell access codes or private channel invites |
| **Whop / Patreon** | Recurring | Subscription tiers mapped to channels |
| **Indie Hackers / Product Hunt** | Launch spike | Frame as indie signals tooling, not finance hype |

Affiliate/influencer crypto Telegram ads work for acquisition but burn trust fast if signals spam or underperform — lead with **selectivity** (few good alerts > many).

## Does Telegram-only limit value?

**It limits ceiling, not viability.**

Telegram-only strengths:

- Native push on mobile; crypto natives already live there
- Near-zero UI cost; fast to charge for a private channel
- Easy ops for a solo founder

Telegram-only ceilings:

- **Single-tenant today:** one `TELEGRAM_CHAT_ID` — every paying customer needs their own deployment *or* you build multi-subscriber routing
- Platform risk (bots banned, API limits, no ownership of the relationship graph)
- Harder upsell of dashboards, history search, API webhooks, TradingView webhooks
- Perceived as “hobby grade” vs a branded web app with charts and track record pages
- Worse for B2B / funds who need SSO, audit logs, SLA

**Practical monetization path:**

1. **Now:** Private Telegram channel or shared bot chat — monthly subscription (signal hygiene is the product)
2. **Next:** Multi-chat fan-out + Discord webhook (still thin client, higher ARPU tiers)
3. **Later:** Web track-record page + webhook API so power users pipe into TradingView / their own bots — this is where valuation usually jumps

Telegram-only does **not** block a first $1–5k MRR if the track record and selectivity are real. It **does** block “SaaS multiple” storytelling until you have accounts, billing, and at least one non-Telegram delivery path.

## Suggested offer structure

| Tier | Delivery | Differentiation |
|---|---|---|
| Free teaser | Delayed / subset pairs | Prove value, grow list |
| Pro | Real-time Telegram, top pairs | Cooldown + ranked alerts |
| Desk | Discord + webhook + weekly PDF of stats | Teams / affiliates |

Always include: not financial advice, past backtests ≠ future results, users execute manually on their own exchange accounts.

## Restore or extend live trading

If you later sell execution as a separate product, fork from `v1.0.0-live-trading` — do not mix custody/API-key trading back into the public signals SKU without a clear compliance story.
