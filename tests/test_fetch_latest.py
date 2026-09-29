"""Live OHLCV must be the newest page, not an old window anchored on since."""

from unittest.mock import MagicMock

import pandas as pd


def test_fetch_data_omits_since(monkeypatch):
    mock_ex = MagicMock()
    base = 1_758_000_000_000  # well in the past so every bar is closed
    mock_ex.fetch_ohlcv.return_value = [
        [base + i * 900_000, 1.0, 1.1, 0.9, 1.0, 10.0] for i in range(120)
    ]
    monkeypatch.setattr("utils.exchangeUtils.get_exchange", lambda: mock_ex)

    import bot

    monkeypatch.setattr(bot, "exchange", mock_ex)
    df = bot.fetch_data("ADA/USDT:USDT", "15m", limit=500)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 120
    kwargs = mock_ex.fetch_ohlcv.call_args.kwargs
    assert kwargs["timeframe"] == "15m"
    assert kwargs["limit"] == 500
    assert "since" not in kwargs


def test_fetch_data_htf_page_size(monkeypatch):
    mock_ex = MagicMock()
    base = 1_758_000_000_000
    mock_ex.fetch_ohlcv.return_value = [
        [base + i * 3_600_000, 1.0, 1.1, 0.9, 1.0, 10.0] for i in range(80)
    ]
    monkeypatch.setattr("utils.exchangeUtils.get_exchange", lambda: mock_ex)

    import bot

    monkeypatch.setattr(bot, "exchange", mock_ex)
    df = bot.fetch_data("ADA/USDT:USDT", "1h", limit=200)

    assert len(df) == 80
    assert mock_ex.fetch_ohlcv.call_args.kwargs["limit"] == 200
    assert "since" not in mock_ex.fetch_ohlcv.call_args.kwargs
