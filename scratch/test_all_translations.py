import re
import sys
import os

# Add src to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from db.helpers import AsyncpgConnection

queries = [
    # 1. api.py stocks ingestion query
    """INSERT OR REPLACE INTO stocks (
        ticker, name, sector, industry,
        total_assets, total_debt, cash_equivalents, accounts_receivable,
        total_revenue, interest_income,
        shares_outstanding, avg_market_cap_36mo, raw_info, sec_filing_url, fetched_at
    ) VALUES (
        :ticker, :name, :sector, :industry,
        :total_assets, :total_debt, :cash_equivalents, :accounts_receivable,
        :total_revenue, :interest_income,
        :shares_outstanding, :avg_market_cap_36mo, :raw_info, :sec_filing_url, :fetched_at
    )""",
    
    # 2. api.py manual override query 1
    """
                INSERT OR REPLACE INTO manual_overrides 
                (ticker, haram_revenue_override, debt_ratio_override, cash_ratio_override, interest_income_override, doubtful_revenue_override, reasoning, is_user_override, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
    """,
    
    # 3. db/setup.py shariah_segment_map
    """
                        INSERT OR REPLACE INTO shariah_segment_map 
                        (ticker, segment_name, compliance_status, notes)
                        VALUES (?, ?, ?, ?)
    """,
    
    # 4. db/setup.py proposed_segment_rules
    """
                        INSERT OR REPLACE INTO proposed_segment_rules 
                        (ticker, segment_name, compliance_status, suggested_notes, status, created_at)
                        VALUES (?, ?, ?, ?, 'approved', ?)
    """,
    
    # 5. batch_ai_audit.py manual_overrides
    """
                    INSERT OR REPLACE INTO manual_overrides 
                    (ticker, haram_revenue_override, debt_ratio_override, cash_ratio_override, interest_income_override, doubtful_revenue_override, reasoning, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
]

# We want to mock AsyncpgCursor's run_sync call to just return the translated query and params
class TestCursor:
    def execute(self, query, params=None):
        query = query.strip()
        
        # 1. Translate SQLite metadata queries to Postgres
        if "sqlite_master" in query:
            query = re.sub(r"\bsqlite_master\b", "information_schema.tables", query, flags=re.IGNORECASE)
            select_match = re.search(r"SELECT\s+(.*?)\s+FROM", query, re.DOTALL | re.IGNORECASE)
            if select_match:
                select_cols = select_match.group(1)
                new_select_cols = re.sub(r"\bname\b", "table_name as name", select_cols, flags=re.IGNORECASE)
                query = query.replace(select_cols, new_select_cols, 1)
            parts = re.split(r"\bFROM\b", query, maxsplit=1, flags=re.IGNORECASE)
            if len(parts) == 2:
                parts[1] = re.sub(r"\bname\b", "table_name", parts[1])
                parts[1] = re.sub(r"\btype\b", "table_type", parts[1], flags=re.IGNORECASE)
                parts[1] = re.sub(r"'table'", "'BASE TABLE'", parts[1], flags=re.IGNORECASE)
                parts[1] = re.sub(r"'view'", "'VIEW'", parts[1], flags=re.IGNORECASE)
                query = f"{parts[0]} FROM {parts[1]}"
            if "WHERE" in query:
                query = re.sub(r"\bWHERE\b", "WHERE table_schema='public' AND", query, flags=re.IGNORECASE)
            else:
                query += " WHERE table_schema='public'"

        # 2. Translate SQLite PRAGMA commands
        if "PRAGMA table_info" in query:
            m = re.search(r"PRAGMA table_info\((\w+)\)", query)
            if m:
                table_name = m.group(1)
                query = f"""
                    SELECT 0 as cid, column_name as name, data_type as type,
                            case when is_nullable = 'NO' then 1 else 0 end as notnull,
                            column_default as dflt_value, 0 as pk
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = '{table_name}'
                """

        # 3. Translate SQLite "INSERT OR REPLACE INTO" to Postgres
        if "INSERT OR REPLACE INTO" in query:
            m = re.match(
                r"INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\((.*?)\)\s*VALUES\s*\((.*?)\)",
                query,
                re.DOTALL | re.IGNORECASE
            )
            if m:
                table_name = m.group(1).strip()
                columns_str = m.group(2).strip()
                values_str = m.group(3).strip()
                
                columns = [c.strip() for c in columns_str.split(",")]
                
                if table_name.lower() == "stocks":
                    pkey = "ticker"
                elif table_name.lower() == "manual_overrides":
                    pkey = "ticker"
                elif table_name.lower() in ("shariah_segment_map", "proposed_segment_rules"):
                    pkey = "ticker, segment_name"
                else:
                    pkey = "ticker"
                
                pkey_cols = [pk.strip().lower() for pk in pkey.split(",")]
                update_cols = [c for c in columns if c.lower() not in pkey_cols]
                update_clause = ", ".join([f"{col} = EXCLUDED.{col}" for col in update_cols])
                
                query = f"INSERT INTO {table_name} ({columns_str}) VALUES ({values_str}) ON CONFLICT ({pkey}) DO UPDATE SET {update_clause}"

        # 4. Translate placeholders
        if params is not None:
            if isinstance(params, dict):
                keys_found = re.findall(r":(\w+)", query)
                for idx, key in enumerate(keys_found):
                    query = re.sub(rf":{key}\b", f"${idx+1}", query)
                params = [params[key] for key in keys_found]
            else:
                if isinstance(params, (list, tuple)):
                    params = list(params)
                else:
                    params = [params]
                count = 1
                while "?" in query:
                    query = query.replace("?", f"${count}", 1)
                    count += 1
        else:
            params = []
            
        return query, params

cursor = TestCursor()
mock_dict = {
    'ticker': 'AAPL', 'name': 'Apple', 'sector': 'Tech', 'industry': 'Consumer Electronics',
    'total_assets': 100, 'total_debt': 50, 'cash_equivalents': 20, 'accounts_receivable': 10,
    'total_revenue': 300, 'interest_income': 5, 'shares_outstanding': 15,
    'avg_market_cap_36mo': 2000, 'raw_info': '{}', 'sec_filing_url': 'http://sec', 'fetched_at': '2026'
}
for idx, q in enumerate(queries):
    print(f"\n--- QUERY {idx+1} ---")
    print("Original:")
    print(q.strip())
    translated, params = cursor.execute(q, params=mock_dict if idx == 0 else [1,2,3,4,5,6,7,8,9,10])
    print("Translated:")
    print(translated)
    print("Params:", params)
