import logging
import numpy as np
import pandas as pd
import yfinance as yf
from matplotlib import pyplot as plt
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf

from src.db.helpers import get_db

logger = logging.getLogger(__name__)


def get_data(include_doubtful=False):
    conn = get_db()
    df_halal = pd.read_sql_query("SELECT ticker, sector, purification_per_share FROM halal_universe", conn)
    if include_doubtful:
        df_doubtful = pd.read_sql_query("SELECT ticker, sector, purification_per_share FROM doubtful_universe", conn)
        df_combined = pd.concat([df_halal, df_doubtful], ignore_index=True).drop_duplicates(subset=["ticker"])
    else:
        df_combined = df_halal
    conn.close()

    tickers = df_combined["ticker"].tolist()
    sector_map = dict(zip(df_combined["ticker"], df_combined["sector"]))
    purification_map = dict(zip(df_combined["ticker"], df_combined["purification_per_share"]))

    if not tickers:
        raise ValueError("No halal universe found. Run the screener first.")

    data = yf.download(tickers, period="2y", interval="1d", auto_adjust=True)
    if isinstance(data.columns, pd.MultiIndex):
        data = data["Close"]
    elif "Close" in data.columns:
        data = data["Close"]
    
    prices = data.dropna(axis=1, how="any")
    # Filter maps to only include tickers that have price data
    filtered_sector_map = {t: sector_map[t] for t in prices.columns}
    filtered_purification_map = {t: purification_map[t] for t in prices.columns}
    
    return prices, filtered_sector_map, filtered_purification_map


def get_portfolio_stats(weights, log_returns, cov_matrix):
    port_return = np.sum(log_returns.mean() * weights) * 252
    port_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
    return port_return, port_vol


def calculate_var(weights, log_returns, confidence=0.95, horizon_days=1):
    """
    Calculate Value-at-Risk using historical simulation.

    Computes portfolio daily P&L from historical log returns and the given
    weight vector, sorts them ascending, and returns the (1 - confidence)-th
    percentile as a positive loss value.  For multi-day horizons the daily
    VaR is scaled by sqrt(horizon_days) (square-root-of-time rule).

    Args:
        weights: Array of portfolio weights summing to 1.
        log_returns: DataFrame of daily log returns (rows = days, cols = assets).
        confidence: Confidence level for VaR (default 0.95 → 95 %).
        horizon_days: Holding-period horizon in trading days (default 1).

    Returns:
        Positive float representing the estimated maximum loss at the given
        confidence level over the specified horizon (as a fraction of
        portfolio value, e.g. 0.02 = 2 %).
    """
    # Portfolio daily P&L series (each day's weighted sum of log returns)
    portfolio_returns = log_returns.values @ np.asarray(weights)
    # (1 - confidence)-th percentile gives the loss threshold
    var_daily = -np.percentile(portfolio_returns, (1 - confidence) * 100)
    return float(var_daily * np.sqrt(horizon_days))


def objective(weights, log_returns, cov_matrix, strategy="Max Sharpe"):
    port_return, port_vol = get_portfolio_stats(weights, log_returns, cov_matrix)
    if strategy == "Min Volatility" or strategy == "Target Return":
        return port_vol
    elif strategy == "Target Volatility":
        return -port_return
    # Default to Max Sharpe Ratio
    return -port_return / port_vol


def run_optimizer(
    max_weight=0.10,
    sector_cap=0.30,
    strategy="Max Sharpe",
    target_vol=0.15,
    target_ret=0.15,
    include_doubtful=False,
    max_var=0.02,
):
    """
    Run portfolio optimization with risk guardrails.

    Args:
        max_weight: Hard per-asset concentration cap (default 10 %).
        sector_cap: Maximum aggregate weight for any single sector (default 30 %).
        strategy: One of "Max Sharpe", "Min Volatility", "Target Volatility",
                  "Target Return".
        target_vol: Target annualised volatility (used when strategy="Target Volatility").
        target_ret: Target annualised return (used when strategy="Target Return").
        include_doubtful: Whether to include the doubtful universe in the
                          investable set.
        max_var: Maximum allowable daily VaR at 95 % confidence (default 0.02 = 2 %).
                 Enforced as a scipy inequality constraint so the optimiser
                 cannot exceed this threshold.
    """
    if not isinstance(include_doubtful, bool):
        raise TypeError("include_doubtful must be a boolean")
    prices, sector_map, purification_map = get_data(include_doubtful=include_doubtful)
    if prices.empty:
        print("No price data returned. Check the halal universe and try again.")
        return

    # Keep top 50 by average price for stability
    prices = prices[prices.mean().nlargest(50).index]
    log_returns = np.log(prices / prices.shift(1)).dropna()

    lw = LedoitWolf()
    cov_matrix = lw.fit(log_returns).covariance_ * 252

    num_assets = len(log_returns.columns)
    tickers = log_returns.columns

    # Monte Carlo simulation for background cloud
    num_portfolios = 5000
    mc_results = np.zeros((3, num_portfolios))
    for i in range(num_portfolios):
        weights = np.random.random(num_assets)
        weights /= np.sum(weights)
        ret, vol = get_portfolio_stats(weights, log_returns, cov_matrix)
        mc_results[0, i] = ret
        mc_results[1, i] = vol
        mc_results[2, i] = ret / vol

    # Individual Bounds (0 to max_weight)
    bounds = tuple((0, max_weight) for _ in range(num_assets))

    # Basic constraint: weights sum to 1
    constraints = [{"type": "eq", "fun": lambda x: np.sum(x) - 1}]

    # ----- Phase 4.2: VaR constraint -----
    # max_var - calculate_var(x, log_returns) >= 0
    if max_var is not None:
        def var_constraint(x, lr=log_returns, mv=max_var):
            return mv - calculate_var(x, lr)
        constraints.append({"type": "ineq", "fun": var_constraint})

    # Target constraints based on chosen strategy
    if strategy == "Target Volatility":
        # port_vol <= target_vol -> target_vol - port_vol >= 0
        def vol_constraint(x, log_returns=log_returns, cov_matrix=cov_matrix, target=target_vol):
            _, vol = get_portfolio_stats(x, log_returns, cov_matrix)
            return target - vol
        constraints.append({"type": "ineq", "fun": vol_constraint})
    elif strategy == "Target Return":
        # port_return >= target_ret -> port_return - target_ret >= 0
        def ret_constraint(x, log_returns=log_returns, cov_matrix=cov_matrix, target=target_ret):
            ret, _ = get_portfolio_stats(x, log_returns, cov_matrix)
            return ret - target
        constraints.append({"type": "ineq", "fun": ret_constraint})

    # Sector Constraints
    unique_sectors = set(sector_map.values())
    for sector in unique_sectors:
        if not sector: continue
        indices = [i for i, t in enumerate(tickers) if sector_map.get(t) == sector]
        if not indices: continue
        
        def sector_constraint(x, idxs=indices, cap=sector_cap):
            return cap - np.sum(x[idxs])
            
        constraints.append({"type": "ineq", "fun": sector_constraint})

    init_guess = np.ones(num_assets) / num_assets

    optimal = minimize(
        objective,
        init_guess,
        args=(log_returns, cov_matrix, strategy),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
    )

    if not optimal.success:
        print(f"⚠️ Optimization failed: {optimal.message}")
        return None

    # ----- Phase 4.2: Post-optimization concentration cap clipping -----
    final_weights = np.array(optimal.x, dtype=float)
    clipped_tickers = []
    for i in range(len(final_weights)):
        if final_weights[i] > max_weight:
            clipped_tickers.append((str(tickers[i]), float(final_weights[i])))
            final_weights[i] = max_weight
    if clipped_tickers:
        # Re-normalise so weights still sum to 1
        final_weights = final_weights / final_weights.sum()
        for tkr, orig_w in clipped_tickers:
            logger.warning(
                "Concentration cap clipping: %s weight %.4f exceeded max_weight %.4f — clipped and re-normalised.",
                tkr, orig_w, max_weight,
            )
        print(f"⚠️ Concentration cap: clipped {len(clipped_tickers)} asset(s) exceeding {max_weight:.0%} and re-normalised.")

    opt_ret, opt_vol = get_portfolio_stats(final_weights, log_returns, cov_matrix)
    var_95 = calculate_var(final_weights, log_returns, confidence=0.95, horizon_days=1)

    plt.figure(figsize=(10, 6))
    plt.scatter(mc_results[1, :], mc_results[0, :], c=mc_results[2, :], cmap="viridis", s=10, alpha=0.3)
    plt.colorbar(label="Sharpe Ratio")
    plt.scatter(opt_vol, opt_ret, color="red", marker="*", s=200, label="Optimal Portfolio")
    plt.title(f"Efficient Frontier (Strategy: {strategy}, Max Stock: {max_weight:.0%}, Max Sector: {sector_cap:.0%})")
    plt.xlabel("Volatility")
    plt.ylabel("Expected Return")
    plt.legend()
    plt.grid(True)
    plt.savefig("efficient_frontier.png")

    allocation = pd.Series(final_weights, index=tickers)
    allocation = allocation[allocation > 0.001].sort_values(ascending=False)

    print("\n✅ Visualization saved as 'efficient_frontier.png'")
    print(f"🚀 Optimal portfolio expected return: {opt_ret:.2%}, volatility: {opt_vol:.2%}")
    print(f"📊 VaR (95%, 1-day): {var_95:.4f} ({var_95:.2%})")
    
    # Calculate Purification
    total_purification_per_1000 = 0
    for ticker, weight in allocation.items():
        price = prices[ticker].iloc[-1]
        shares = (1000 * weight) / price
        purification = shares * purification_map.get(ticker, 0)
        total_purification_per_1000 += purification

    print(f"✨ Portfolio Purification: ${total_purification_per_1000:.4f} per $1,000 invested")

    sector_sums = {}
    for t, w in allocation.items():
        s = sector_map.get(t, "Unknown")
        sector_sums[s] = sector_sums.get(s, 0) + w

    # Compute max concentration for risk profile reporting
    max_concentration = float(allocation.max()) if not allocation.empty else 0.0

    results = {
        "expected_return": opt_ret,
        "volatility": opt_vol,
        "VaR_95": var_95,
        "max_concentration": max_concentration,
        "purification_per_1000": total_purification_per_1000,
        "allocation": allocation,
        "sector_exposure": pd.Series(sector_sums),
        "prices": {t: float(prices[t].iloc[-1]) for t in allocation.index},
        "purification_map": purification_map
    }

    print("\n--- Sector Exposure ---")
    for s, w in sorted(sector_sums.items(), key=lambda x: x[1], reverse=True):
        print(f"{s}: {w:.2%}")

    print("\n--- Optimal Portfolio Allocation ---")
    for ticker, weight in allocation.items():
        print(f"{ticker}: {weight:.2%}")

    return results


if __name__ == "__main__":
    run_optimizer()