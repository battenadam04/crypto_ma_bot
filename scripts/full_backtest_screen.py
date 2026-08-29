#!/usr/bin/env python3
"""Full top-N backtest screen using Phemex + new range S/R levels (no default fallback)."""
import json
import os
import sys
import time
import types
from datetime import datetime, timedelta, timezone

import ccxt
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

sys.modules.setdefault("pandas_ta", types.ModuleType("pandas_ta"))

import config

config.IS_BACKTESTING = True

from utils.exchangeUtils import get_auto_backtest_pairs
from utils.utils import add_atr_column, calculate_mas
import strategies.simulate_trades as sim


def _fixed_risk(pnl_list):
    r = sim._orig_risk(pnl_list) if hasattr(sim, "_orig_risk") else sim._compute_risk_metrics(pnl_list)
    if "avg_win_pct" not in r:
        r["avg_win_pct"] = round(r.get("avg_win", 0) * 100, 4)
        r["avg_loss_pct"] = round(r.get("avg_loss", 0) * 100, 4)
    return r


sim._orig_risk = sim._compute_risk_metrics
sim._compute_risk_metrics = _fixed_risk
sim._bt_log = lambda *a, **k: None


def _enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = calculate_mas(df)
    df = add_atr_column(df)
    df["rsi"] = RSIIndicator(df["close"], window=14).rsi()
    df["adx"] = ADXIndicator(df["high"], df["low"], df["close"], window=14).adx()
    df["support"] = df["low"].rolling(window=config.SR_LOOKBACK_BARS).min()
    df["resistance"] = df["high"].rolling(window=config.SR_LOOKBACK_BARS).max()
    return df


def _fetch_ohlcv(ex, pair, timeframe, days):
    step_ms = sim._timeframe_step_ms(timeframe)
    since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
    limit = sim._backtest_ohlcv_limit()
    target = max(
        300,
        sim._approx_bars_per_calendar_day(timeframe) * max(1, int(days)),
    )
    rows = []
    loops = 0
    while loops < 80 and len(rows) < target:
        chunk = ex.fetch_ohlcv(pair, timeframe=timeframe, since=since, limit=limit)
        if not chunk:
            break
        rows.extend(chunk)
        since = chunk[-1][0] + step_ms
        loops += 1
        time.sleep(config.BACKTEST_FETCH_SLEEP_SEC)
        if len(chunk) < limit - 5:
            break
    if not rows:
        return pd.DataFrame()
    seen = set()
    uniq = []
    for row in rows:
        if row[0] not in seen:
            uniq.append(row)
            seen.add(row[0])
    df = pd.DataFrame(uniq, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return _enrich(df)


def _patch_fetch(ex):
    def fetch_data(pair, timeframe=config.TIMEFRAME, days=config.BACKTEST_DAYS):
        return _fetch_ohlcv(ex, pair, timeframe, days)

    def fetch_htf(pair, timeframe=config.HTF_TIMEFRAME, days=config.BACKTEST_DAYS):
        return _fetch_ohlcv(ex, pair, timeframe, days)

    sim.fetch_data = fetch_data
    sim.fetch_higher_timeframe_data = fetch_htf
    sim._get_exchange = lambda: ex


def _qualifies(result, threshold, min_trades, min_rr, enforce_rr):
    trades = int(result.get("total_trades") or 0)
    wr = float(result.get("win_rate") or 0)
    rr = float(result.get("rr_ratio") or 0)
    if trades < min_trades:
        return False
    if wr < threshold:
        return False
    if enforce_rr and rr < min_rr:
        return False
    return True


def main():
    ex = ccxt.phemex({"enableRateLimit": True})
    ex.load_markets()
    _patch_fetch(ex)

    pairs = get_auto_backtest_pairs(ex)
    if not pairs:
        print("ERROR: auto discovery returned 0 pairs — refusing to fall back to defaults.")
        sys.exit(1)

    symbols = [p[0] if isinstance(p, (list, tuple)) else p for p in pairs]
    threshold = float(config.BACKTEST_WIN_RATE_THRESHOLD)
    min_trades = max(2, int(config.BACKTEST_MIN_TRADES))
    min_rr = float(config.BACKTEST_MIN_RR_RATIO)
    enforce_rr = bool(config.BACKTEST_ENFORCE_RR)
    days = int(config.BACKTEST_DAYS)

    print(
        f"Screening {len(symbols)} Phemex pairs ({days}d, threshold ≥{threshold}%, "
        f"min trades {min_trades}, enforce RR={enforce_rr})\n",
        flush=True,
    )
    print(f"{'#':>3} {'Pair':<22} {'WR':>7} {'Trades':>7} {'Range':>6} {'MA':>5} {'Qual':>5}")
    print("-" * 62, flush=True)

    results = {}
    qualified = []
    errors = 0

    for i, sym in enumerate(symbols, 1):
        try:
            df = sim.fetch_data(sym, config.TIMEFRAME, days=days)
            htf = sim.fetch_higher_timeframe_data(sym, config.HTF_TIMEFRAME, days=days)
            if len(df) < 300 or len(htf) < 50:
                print(f"{i:3d} {sym:<22} {'—':>7} {'skip':>7} {'—':>6} {'—':>5} {'—':>5}", flush=True)
                continue
            r = sim.simulate_combined_strategy(sym, df, htf)
            results[sym] = {k: v for k, v in r.items() if k != "equity_curve"}
            ok = _qualifies(r, threshold, min_trades, min_rr, enforce_rr)
            if ok:
                qualified.append(sym)
            mark = "✓" if ok else "✗"
            print(
                f"{i:3d} {sym:<22} {r['win_rate']:6.1f}% {r['total_trades']:7d} "
                f"{r.get('range_used', 0):6d} {r.get('ma_used', 0):5d} {mark:>5}",
                flush=True,
            )
        except Exception as e:
            errors += 1
            print(f"{i:3d} {sym:<22} ERROR: {e}", flush=True)

    print("-" * 62, flush=True)
    print(f"\nQualified: {len(qualified)} / {len(symbols)} screened", flush=True)
    if qualified:
        print("Watchlist:", ", ".join(qualified), flush=True)
    else:
        near = sorted(
            [(s, r) for s, r in results.items() if r.get("total_trades", 0) >= min_trades],
            key=lambda x: x[1].get("win_rate", 0),
            reverse=True,
        )[:8]
        if near:
            print("\nNear-misses (have min trades, below threshold):", flush=True)
            for s, r in near:
                print(f"  {s}: {r['win_rate']}% ({r['total_trades']} trades)", flush=True)

    out = {
        "pairs": qualified,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "win_rate_threshold": threshold,
        "screened": len(symbols),
        "errors": errors,
        "results": results,
    }
    out_path = os.path.join(ROOT, "last_backtest_screen.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {out_path}", flush=True)


if __name__ == "__main__":
    main()
