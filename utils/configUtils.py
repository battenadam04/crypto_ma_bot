# Strategy-specific configs
strategy_settings = {
    "trend": {
        "atr_tp": 2.0,            # Reduced from 6.0
        "atr_sl": 1.5,            # Reduced from 4.0
        "min_tp_pct": 0.01,       # 1.0%
        "min_sl_pct": 0.006       # 0.6%
    },
    "range": {
        "atr_tp": 1.6,            # Reduced from 5.0
        "atr_sl": 1.2,            # Reduced from 3.8
        "min_tp_pct": 0.008,      # 0.8%
        "min_sl_pct": 0.005       # 0.5%
    },
    "scalp": {
        "atr_tp": 1.4,            # Reduced from 3.2
        "atr_sl": 1.0,            # Reduced from 2.5
        "min_tp_pct": 0.005,      # 0.5%
        "min_sl_pct": 0.003       # 0.3%
    }
}
