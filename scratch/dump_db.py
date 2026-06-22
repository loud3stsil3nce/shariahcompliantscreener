import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.db.helpers import get_db

def main():
    conn = get_db()
    
    print("=== SHARIAH SEGMENT MAP ===")
    cursor = conn.execute("SELECT * FROM shariah_segment_map")
    for r in cursor.fetchall():
        print(dict(zip(r.keys(), r.values)))
        
    print("\n=== GLOBAL SEGMENT PATTERNS ===")
    cursor = conn.execute("SELECT * FROM global_segment_patterns")
    for r in cursor.fetchall():
        print(dict(zip(r.keys(), r.values)))
        
    print("\n=== MANUAL OVERRIDES FOR AAPL ===")
    cursor = conn.execute("SELECT * FROM manual_overrides WHERE ticker = 'AAPL'")
    for r in cursor.fetchall():
        print(dict(zip(r.keys(), r.values)))

    print("\n=== CURATED BENCHMARKS FOR AAPL ===")
    cursor = conn.execute("SELECT * FROM curated_benchmarks WHERE ticker = 'AAPL'")
    for r in cursor.fetchall():
        print(dict(zip(r.keys(), r.values)))

if __name__ == "__main__":
    main()
