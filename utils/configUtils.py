# Asymmetric R:R: TP distance > SL so break-even win rate stays realistic (~35%).
strategy_settings = {
    "trend": {
        "atr_tp": 3.2,
        "atr_sl": 1.2,
        "min_tp_pct": 0.012,    # 1.2%
        "min_sl_pct": 0.0055,   # 0.55%
    },
    "range": {
        "atr_tp": 2.4,
        "atr_sl": 1.0,
        "min_tp_pct": 0.009,    # 0.9%
        "min_sl_pct": 0.0045,   # 0.45%
    },
    "scalp": {
        "atr_tp": 2.0,
        "atr_sl": 1.0,
        "min_tp_pct": 0.008,
        "min_sl_pct": 0.003,
    },
}
