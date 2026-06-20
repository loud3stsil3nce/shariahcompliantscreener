import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from pandas import Timestamp
import pytest

from src.analysis.optimizer import get_data, get_portfolio_stats, objective


def create_halal_universe_db(path: Path):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE halal_universe (ticker TEXT PRIMARY KEY, sector TEXT, purification_per_share REAL)"
    )
    conn.executemany(
        "INSERT INTO halal_universe (ticker, sector, purification_per_share) VALUES (?, ?, ?)",
        [("AAPL", "Technology", 0.01), ("MSFT", "Healthcare", 0.02)],
    )
    conn.commit()
    conn.close()


def test_get_portfolio_stats():
    prices = pd.DataFrame(
        {
            "AAPL": [100.0, 102.0, 101.0],
            "MSFT": [200.0, 202.0, 204.0],
        },
        index=[Timestamp("2026-01-01"), Timestamp("2026-01-02"), Timestamp("2026-01-03")],
    )
    log_returns = np.log(prices / prices.shift(1)).dropna()
    cov_matrix = np.cov(log_returns.T) * 252
    weights = np.array([0.5, 0.5])

    expected_return = np.sum(log_returns.mean() * weights) * 252
    expected_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))

    port_return, port_vol = get_portfolio_stats(weights, log_returns, cov_matrix)

    assert port_return == pytest.approx(expected_return)
    assert port_vol == pytest.approx(expected_vol)


def test_objective_is_negative_sharpe():
    prices = pd.DataFrame(
        {
            "AAPL": [100.0, 102.0, 101.0],
            "MSFT": [200.0, 202.0, 204.0],
        },
        index=[Timestamp("2026-01-01"), Timestamp("2026-01-02"), Timestamp("2026-01-03")],
    )
    log_returns = np.log(prices / prices.shift(1)).dropna()
    cov_matrix = np.cov(log_returns.T) * 252
    weights = np.array([0.25, 0.75])

    expected_return, expected_vol = get_portfolio_stats(weights, log_returns, cov_matrix)
    assert objective(weights, log_returns, cov_matrix) == pytest.approx(-expected_return / expected_vol)


def test_get_data_reads_close_prices(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    create_halal_universe_db(db_path)

    def fake_get_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def fake_download(tickers, period, interval, auto_adjust):
        columns = pd.MultiIndex.from_product([["Close"], tickers])
        return pd.DataFrame(
            [
                [100.0, 200.0],
                [101.0, 202.0],
            ],
            columns=columns,
            index=[Timestamp("2026-01-01"), Timestamp("2026-01-02")],
        )

    monkeypatch.setattr("src.analysis.optimizer.get_db", fake_get_db)
    monkeypatch.setattr("src.analysis.optimizer.yf.download", fake_download)

    df, sector_map, purification_map = get_data()

    assert list(df.columns) == ["AAPL", "MSFT"]
    assert df.iloc[0].tolist() == [100.0, 200.0]
    assert sector_map["AAPL"] == "Technology"
    assert purification_map["AAPL"] == 0.01


def test_run_optimizer_strategies(tmp_path, monkeypatch):
    db_path = tmp_path / "test_opt.db"
    create_halal_universe_db(db_path)

    def fake_get_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def fake_download(tickers, period, interval, auto_adjust):
        # We need enough prices with fluctuations to calculate a non-singular covariance matrix
        dates = pd.date_range(start="2026-01-01", periods=15, freq="D")
        np.random.seed(42)
        aapl_rets = np.random.normal(0.001, 0.02, 15)
        msft_rets = np.random.normal(0.0015, 0.02, 15)
        return pd.DataFrame(
            {
                "AAPL": 100.0 * np.cumprod(1.0 + aapl_rets),
                "MSFT": 200.0 * np.cumprod(1.0 + msft_rets),
            },
            index=dates,
        )

    monkeypatch.setattr("src.analysis.optimizer.get_db", fake_get_db)
    monkeypatch.setattr("src.analysis.optimizer.yf.download", fake_download)
    # Mock plt.savefig so it doesn't try to write to filesystem or fails
    monkeypatch.setattr("src.analysis.optimizer.plt.savefig", lambda *args, **kwargs: None)

    from src.analysis.optimizer import run_optimizer

    for strategy in ["Max Sharpe", "Min Volatility", "Target Volatility", "Target Return"]:
        res = run_optimizer(
            max_weight=1.0,
            sector_cap=1.0,
            strategy=strategy,
            target_vol=0.20,
            target_ret=0.05
        )
        assert res is not None
        assert "expected_return" in res
        assert "volatility" in res
        assert "allocation" in res
        assert "sector_exposure" in res
        assert len(res["allocation"]) > 0