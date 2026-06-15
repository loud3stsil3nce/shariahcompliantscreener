import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf
from .utils import get_db

def get_historical_prices(tickers, start_date, end_date):
    """Fetch historical prices for tickers and the benchmark (SPY)."""
    all_tickers = list(tickers) + ["SPY"]
    try:
        data = yf.download(all_tickers, start=start_date, end=end_date, interval="1d", auto_adjust=True, progress=False)
        if isinstance(data.columns, pd.MultiIndex):
            data = data["Close"]
        return data.dropna(axis=1, how="all").ffill()
    except Exception as e:
        print(f"❌ YFinance download failed: {e}")
        return pd.DataFrame()

def optimize_historical(prices, max_weight=0.10):
    """Run the optimization logic on a specific window of price data."""
    log_returns = np.log(prices / prices.shift(1)).dropna()
    if log_returns.empty:
        return None
        
    num_assets = len(prices.columns)
    
    # MATH FIX: If N * max_weight < 1, the optimizer will fail (infeasible).
    # We must ensure max_weight is at least 1/N.
    safe_max_weight = max(max_weight, (1.1 / num_assets)) 
    
    try:
        lw = LedoitWolf()
        cov_matrix = lw.fit(log_returns).covariance_ * 252
        mean_returns = log_returns.mean() * 252
    except Exception as e:
        print(f"❌ Math calculation failed: {e}")
        return None
    
    def objective(w):
        p_ret = np.sum(mean_returns * w)
        p_vol = np.sqrt(np.dot(w.T, np.dot(cov_matrix, w)))
        if p_vol <= 0: return 0
        return -p_ret / p_vol

    bounds = tuple((0, safe_max_weight) for _ in range(num_assets))
    constraints = [{"type": "eq", "fun": lambda x: np.sum(x) - 1}]
    init_guess = np.ones(num_assets) / num_assets
    
    res = minimize(objective, init_guess, method="SLSQP", bounds=bounds, constraints=constraints)
    
    if not res.success:
        # Fallback to equal weight if optimization fails
        print(f"⚠️ Optimization failed ({res.message}). Falling back to equal weight.")
        return init_guess
        
    return res.x

def run_backtest(test_months=12, train_months=12):
    """
    Simulate: 
    1. Optimize on the 'Train' period.
    2. Hold that portfolio during the 'Test' period.
    3. Compare vs SPY.
    """
    conn = get_db()
    tickers = pd.read_sql_query("SELECT ticker FROM halal_universe", conn)["ticker"].tolist()
    conn.close()
    
    if not tickers:
        return "❌ No halal stocks found. Run screener first."

    # Date math
    end_date = pd.Timestamp.now()
    mid_date = end_date - pd.DateOffset(months=test_months)
    start_date = mid_date - pd.DateOffset(months=train_months)
    
    print(f"📊 Fetching data: {start_date.date()} to {end_date.date()}...")
    prices = get_historical_prices(tickers, start_date, end_date)
    
    if prices.empty or "SPY" not in prices.columns:
        return "❌ Failed to fetch historical price data."
        
    spy_prices = prices["SPY"]
    stock_prices = prices.drop(columns=["SPY"])
    
    # CRITICAL FIX: Only keep stocks that have price data for the ENTIRE period
    # This avoids NaNs that break the math
    full_history_stocks = stock_prices.dropna(axis=1, how="any")
    
    if len(full_history_stocks.columns) < 2:
        return f"❌ Only {len(full_history_stocks.columns)} stocks have full history for this period. Need at least 2."

    # Split into Train and Test
    train_prices = full_history_stocks.loc[start_date:mid_date]
    test_prices = full_history_stocks.loc[mid_date:end_date]
    
    if train_prices.empty or test_prices.empty:
        return "❌ Insufficient price data for the requested dates."

    print(f"⚖️ Optimizing on {len(full_history_stocks.columns)} stocks...")
    weights = optimize_historical(train_prices)
    if weights is None:
        return "❌ Portfolio optimization failed. Try a smaller window or check data."
        
    # Calculate Returns
    test_returns = test_prices.pct_change().dropna()
    portfolio_daily_returns = (test_returns * weights).sum(axis=1)
    portfolio_cum_returns = (1 + portfolio_daily_returns).cumprod()
    
    spy_test_returns = spy_prices.loc[mid_date:end_date].pct_change().dropna()
    spy_cum_returns = (1 + spy_test_returns).cumprod()
    
    port_total_ret = portfolio_cum_returns.iloc[-1] - 1
    spy_total_ret = spy_cum_returns.iloc[-1] - 1
    
    plt.figure(figsize=(12, 6))
    plt.plot(portfolio_cum_returns, label=f"Halal Portfolio ({port_total_ret:.1%})", color="green", linewidth=2)
    plt.plot(spy_cum_returns, label=f"S&P 500 (SPY) ({spy_total_ret:.1%})", color="red", linestyle="--", alpha=0.7)
    
    plt.title(f"Backtest: Halal Portfolio vs S&P 500 ({test_window if 'test_window' in locals() else test_months} Months)")
    plt.xlabel("Date")
    plt.ylabel("Cumulative Return")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.savefig("backtest_results.png")
    
    stats = {
        "portfolio_return": port_total_ret,
        "spy_return": spy_total_ret,
        "outperformance": port_total_ret - spy_total_ret,
        "sharpe": (portfolio_daily_returns.mean() / portfolio_daily_returns.std()) * np.sqrt(252)
    }
    
    return stats

if __name__ == "__main__":
    results = run_backtest()
    print(results)
