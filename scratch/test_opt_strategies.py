import sqlite3
import numpy as np
import pandas as pd
from pathlib import Path
from src.optimizer import run_optimizer
import matplotlib
matplotlib.use('Agg')

# Setup mock DB with different sectors
db_path = Path("scratch/test_opt_debug.db")
if db_path.exists():
    db_path.unlink()
conn = sqlite3.connect(db_path)
conn.execute("CREATE TABLE halal_universe (ticker TEXT PRIMARY KEY, sector TEXT, purification_per_share REAL)")
conn.executemany(
    "INSERT INTO halal_universe (ticker, sector, purification_per_share) VALUES (?, ?, ?)",
    [("AAPL", "Technology", 0.01), ("MSFT", "Healthcare", 0.02)],
)
conn.commit()
conn.close()

# Mock helpers
def fake_get_db():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def fake_download(tickers, period, interval, auto_adjust):
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

import src.optimizer
src.optimizer.get_db = fake_get_db
src.optimizer.yf.download = fake_download
import matplotlib.pyplot as plt
plt.savefig = lambda *args, **kwargs: None

for strategy in ["Max Sharpe", "Min Volatility", "Target Volatility", "Target Return"]:
    print(f"\n--- Strategy: {strategy} ---")
    res = run_optimizer(
        max_weight=1.0,
        sector_cap=1.0,
        strategy=strategy,
        target_vol=0.20,
        target_ret=0.05
    )
    print("Result:", "Success" if res else "Failed")
