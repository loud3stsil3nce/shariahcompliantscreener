import sys
import os
import pandas as pd

# Add src to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from db.helpers import get_db

# Create a small DataFrame
df = pd.DataFrame([{"ticker": "TEST", "name": "Test Company"}])

conn = get_db()
try:
    print("Calling to_sql...")
    df.to_sql("test_table", conn, if_exists="replace", index=False)
    print("to_sql completed successfully!")
except Exception as e:
    import traceback
    print("to_sql failed with:")
    traceback.print_exc()
finally:
    conn.close()
