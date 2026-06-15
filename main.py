import argparse

from src.ingestion import run_ingestion
from src.optimizer import run_optimizer
from src.screener import run_screener


def run_delete(ticker):
    import sqlite3
    ticker = ticker.upper().strip()
    conn = sqlite3.connect('data/halal_screener.db')
    try:
        c1 = conn.execute("DELETE FROM stocks WHERE ticker = ?", (ticker,)).rowcount
        c2 = conn.execute("DELETE FROM manual_overrides WHERE ticker = ?", (ticker,)).rowcount
        conn.commit()
        print(f"🗑️ Deleted {ticker} from database:")
        print(f"  - Stocks table: {c1} row(s) deleted")
        print(f"  - Manual overrides table: {c2} row(s) deleted")
        
        # Run screener to update the tables
        run_screener()
        print("✨ Screener updated successfully!")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Run the shariah compliance stock screener pipeline."
    )
    parser.add_argument("command", choices=["ingest", "screener", "optimize", "delete"])
    parser.add_argument("--refresh", action="store_true", help="Refetch all tickers")
    parser.add_argument("--ticker", type=str, help="Ticker to delete (required for 'delete')")
    args = parser.parse_args()

    if args.command == "ingest":
        run_ingestion(refresh=args.refresh)
    elif args.command == "screener":
        run_screener()
    elif args.command == "optimize":
        run_optimizer()
    elif args.command == "delete":
        if not args.ticker:
            print("❌ Error: --ticker <TICKER> is required for the delete command.")
        else:
            run_delete(args.ticker)


if __name__ == "__main__":
    main()