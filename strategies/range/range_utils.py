def check_range_trade(df):
    last = df.iloc[-1]

    buy_signal = (
        last['close'] <= last['support'] * 1.01  # Near support (1% buffer)
        and last['rsi'] < 30  # Oversold
    )

    sell_signal = (
        last['close'] >= last['resistance'] * 0.99  # Near resistance (1% buffer)
        and last['rsi'] > 70  # Overbought
    )

    return buy_signal, sell_signal

def calculate_sl_tp(entry_price, support, resistance, risk_reward=2):
    sl = entry_price - (entry_price - support) * 0.5  # Stop loss at midpoint to support
    tp = entry_price + (resistance - entry_price) * risk_reward  # TP based on R:R ratio
    return sl, tp

def is_ranging_market(df):
    last = df.iloc[-1]
    return last['adx'] < 25  # Low ADX = sideways market