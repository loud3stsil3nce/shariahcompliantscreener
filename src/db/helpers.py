import asyncio                                                                                                
import asyncpg                                                                                                
import os                                                                                                     
import re                                                                                                     
import pandas as pd                                                                                           
import nest_asyncio                                                                                           
                                                                                                                
DATABASE_URL = os.getenv("DATABASE_URL")                                                                      
if not DATABASE_URL:                                                                                          
    DATABASE_URL = "postgresql://Rafiur:Rafiur123@localhost:5433/db_screener"                                 
                                                                                                                
# 1. Clean for raw asyncpg connection (requires postgresql:// or postgres://)                                 
if DATABASE_URL.startswith("postgresql+asyncpg://"):                                                          
    RAW_DB_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")                               
else:                                                                                                         
    RAW_DB_URL = DATABASE_URL                                                                                 
                                                                                                                
# 2. Clean for SQLAlchemy create_async_engine (requires postgresql+asyncpg://)                                
if DATABASE_URL.startswith("postgresql://"):                                                                  
    ASYNC_DB_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")                             
elif DATABASE_URL.startswith("postgres://"):                                                                  
    ASYNC_DB_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://")                               
else:                                                                                                         
    ASYNC_DB_URL = DATABASE_URL                                                                               
                                                                                                                
DB_PATH = "data/halal_screener.db" 
                                                                                                             
def run_sync(coro):                                                                                           
    """Utility to run async coroutines synchronously within any thread (including Streamlit)."""              
    try:                                                                                                      
        loop = asyncio.get_event_loop()                                                                       
    except RuntimeError:                                                                                      
        loop = asyncio.new_event_loop()                                                                       
        asyncio.set_event_loop(loop)                                                                          
                                                                                                                
    if loop.is_running():                                                                                     
        nest_asyncio.apply()                                                                                  
    return loop.run_until_complete(coro)                                                                      
                                                                                                                
class RowWrapper:                                                                                             
    """Wrapper to mimic sqlite3.Row for indexing by column name or integer position."""                       
    def __init__(self, desc, values):                                                                         
        self.desc = desc                                                                                      
        self.values = values                                                                                  
        self.keys_list = [d[0] for d in desc]                                                                 
                                                                                                                
    def __getitem__(self, idx):                                                                               
        if isinstance(idx, int):                                                                              
            return self.values[idx]                                                                           
        elif isinstance(idx, str):                                                                            
            try:                                                                                              
                return self.values[self.keys_list.index(idx)]                                                 
            except ValueError:                                                                                
                raise KeyError(idx)                                                                           
        raise TypeError("Indices must be integers or strings")                                                
                                                                                                                
    def __len__(self):                                                                                        
        return len(self.values)                                                                               
                                                                                                                
    def keys(self):                                                                                           
        return self.keys_list                                                                                 
                                                                                                                
class AsyncpgCursor:                                                                                          
    def __init__(self, conn_wrapper, query=None):                                                             
        self.conn_wrapper = conn_wrapper                                                                      
        self.description = []                                                                                 
        self.rows = []                                                                                        
        self.idx = 0                                                                                          
        self.rowcount = -1                                                                                    
        if query:                                                                                             
            self.execute(query)                                                                               

                                                                                                                
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
                                                                                                                
        # 2. Translate SQLite PRAGMA commands to standard Postgres column checks                              
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
                                                                                                                
        # 3. Translate SQLite "INSERT OR REPLACE INTO" to Postgres "INSERT INTO ... ON CONFLICT (...) DO UPDATE SET ..."
        if re.search(r"\bINSERT\s+OR\s+REPLACE\s+INTO\b", query, re.IGNORECASE):
            m = re.search(
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
                
                translated_stmt = f"INSERT INTO {table_name} ({columns_str}) VALUES ({values_str}) ON CONFLICT ({pkey}) DO UPDATE SET {update_clause}"
                query = query.replace(m.group(0), translated_stmt)

        # 4. Translate sqlite parameter placeholders to postgres ($1, $2, ...)
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
                                                                                                                
        async def _execute():                                                                                 
            conn = await asyncpg.connect(dsn=RAW_DB_URL)                                                    
            try:                                                                                              
                results = await conn.fetch(query, *params)                                                    
                return results                                                                                
            finally:                                                                                          
                await conn.close()                                                                            
                                                                                                                
        records = run_sync(_execute())                                                                        
                                                                                                                
        if records:                                                                                           
            # description is required for pandas DataFrame generation                                         
            self.description = [(key, None, None, None, None, None, None) for key in records[0].keys()]       
            self.rows = [list(r.values()) for r in records]                                                   
            self.rowcount = len(records)                                                                      
        else:                                                                                                 
            self.description = []                                                                             
            self.rows = []                                                                                    
            self.rowcount = 0                                                                                 
        self.idx = 0                                                                                          
        return self                                                                                           
                                                                                                                
    def executemany(self, query, params_list):                                                                
        for params in params_list:                                                                            
            self.execute(query, params)                                                                       
        self.rowcount = len(params_list)                                                                      
        return self                                                                                           
                                                                                                                
    def fetchone(self):                                                                                       
        if self.idx < len(self.rows):                                                                         
            r = self.rows[self.idx]                                                                           
            self.idx += 1                                                                                     
            return RowWrapper(self.description, r)                                                            
        return None                                                                                           
                                                                                                                
    def fetchall(self):                                                                                       
        res = [RowWrapper(self.description, r) for r in self.rows[self.idx:]]                                 
        self.idx = len(self.rows)                                                                             
        return res                                                                                            
                                                                                                                
    def close(self):                                                                                          
        pass                                                                                                  
                                                                                                                
class AsyncpgConnection:                                                                                      
    """Wrapper that mimics a synchronous sqlite3 connection."""                                               
    def cursor(self):                                                                                         
        return AsyncpgCursor(self)                                                                            
                                                                                                                
    def execute(self, query, params=None):                                                                    
        cur = self.cursor()                                                                                   
        cur.execute(query, params)                                                                            
        return cur                                                                                            
                                                                                                                
    def executescript(self, script):                                                                          
        statements = [s.strip() for s in script.split(";") if s.strip()]                                      
        for stmt in statements:                                                                               
            self.execute(stmt)                                                                                
                                                                                                                
    def executemany(self, query, params_list):                                                                
        for params in params_list:                                                                            
            self.execute(query, params)                                                                       
                                                                                                                
    def commit(self):                                                                                         
        pass                                                                                                  
                                                                                                                
    def close(self):                                                                                          
        pass      
    
    def rollback(self):
        pass                                                                                            
                                                                                                                
def get_db():                                                                                                 
    return AsyncpgConnection()

