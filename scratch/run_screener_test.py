import sys
import os

# Add project root to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.analysis.screener import run_screener

try:
    print("Running screener...")
    run_screener()
    print("Screener completed successfully!")
except Exception as e:
    import traceback
    traceback.print_exc()
