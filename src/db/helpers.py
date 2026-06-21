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
        if query:                                                                                             
            self.execute(query)                                                                               
                                                                                                                
    def execute(self, query, params=None):                                                                    
        # 1. Translate SQLite metadata queries to Postgres                                                    
        if "sqlite_master" in query:
            query = query.replace("sqlite_master", "information_schema.tables")
            query = query.replace("name FROM", "table_name as name FROM")
            query = query.replace("type='table' AND", "")
            query = re.sub(r"\bname\s*=\s*", "table_name=", query)
            if "WHERE" in query:
                query = query.replace("WHERE", "WHERE table_schema='public' AND")
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
                                                                                                                
        # 3. Translate sqlite parameter placeholder (?) to postgres parameter placeholder ($1, $2, ...)       
        if params:                                                                                            
            count = 1                                                                                         
            # Replace ? with $1, $2, etc., one by one                                                         
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
        else:                                                                                                 
            self.description = []                                                                             
            self.rows = []                                                                                    
        self.idx = 0                                                                                          
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

