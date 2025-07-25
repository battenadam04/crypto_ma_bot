# Strategy-specific configs
strategy_settings = {
    "trend": {
        "atr_tp": 3.0,          # More generous profit target
        "atr_sl": 1.5,          # Keep same or slightly lower
        "min_tp_pct": 0.012,    # 1.2%
        "min_sl_pct": 0.006     # 0.6%
    },
    "range": {
        "atr_tp": 2.4,
        "atr_sl": 1.2,
        "min_tp_pct": 0.01,     # 1%
        "min_sl_pct": 0.005
    },
    "scalp": {
        "atr_tp": 2.0,
        "atr_sl": 1.0,
        "min_tp_pct": 0.008,
        "min_sl_pct": 0.003
    }
}
