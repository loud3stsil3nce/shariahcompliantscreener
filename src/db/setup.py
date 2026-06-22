import pandas as pd                                                                                           
from src.db.helpers import get_db, run_sync, ASYNC_DB_URL, AsyncpgConnection                                                    
from src.db.models import Base                                                                                
from sqlalchemy.ext.asyncio import create_async_engine                                                        
                                                                                                               
# Initialize database tables if they don't exist                                                              
def init_db_tables():                                                                                         
    conn = get_db() 
    # A. If we are running tests (monkeypatched to return a SQLite connection), run SQLite DDL                
    if hasattr(conn, "executescript") and not isinstance(conn, AsyncpgConnection):                            
        conn.executescript("""                                                                                
            CREATE TABLE IF NOT EXISTS stocks (                                                               
                ticker TEXT PRIMARY KEY,                                                                      
                name TEXT,                                                                                    
                sector TEXT,                                                                                  
                industry TEXT,                                                                                
                total_assets REAL,                                                                            
                total_debt REAL,                                                                              
                cash_equivalents REAL,                                                                        
                accounts_receivable REAL,                                                                     
                total_revenue REAL,                                                                           
                interest_income REAL,                                                                         
                shares_outstanding REAL,                                                                      
                avg_market_cap_36mo REAL,                                                                     
                raw_info TEXT,                                                                                
                sec_filing_url TEXT,                                                                          
                fetched_at TEXT                                                                               
            );                                                                                                
            CREATE TABLE IF NOT EXISTS ai_overrides (                                                         
                ticker TEXT PRIMARY KEY,                                                                      
                haram_revenue_estimate REAL,                                                                  
                reasoning TEXT,                                                                               
                segments_found TEXT,                                                                          
                updated_at TEXT                                                                               
            );                                                                                                
            CREATE TABLE IF NOT EXISTS manual_overrides (                                                     
                ticker TEXT PRIMARY KEY,                                                                      
                haram_revenue_override REAL,                                                                  
                debt_ratio_override REAL,                                                                     
                cash_ratio_override REAL,                                                                     
                receivables_ratio_override REAL,                                                              
                tangibility_ratio_override REAL,                                                              
                interest_income_override REAL,                                                                
                doubtful_revenue_override REAL,                                                               
                reasoning TEXT,                                                                               
                is_user_override INTEGER DEFAULT 0,                                                           
                updated_at TEXT                                                                               
            );                                                                                                
            CREATE TABLE IF NOT EXISTS halal_universe (                                                       
                ticker TEXT PRIMARY KEY,                                                                      
                name TEXT,                                                                                    
                sector TEXT,                                                                                  
                industry TEXT,                                                                                
                total_assets REAL,                                                                            
                total_debt REAL,                                                                              
                cash_equivalents REAL,                                                                        
                accounts_receivable REAL,                                                                     
                total_revenue REAL,                                                                           
                interest_income REAL,                                                                         
                shares_outstanding REAL,                                                                      
                avg_market_cap_36mo REAL,                                                                     
                raw_info TEXT,                                                                                
                sec_filing_url TEXT,                                                                          
                fetched_at TEXT,                                                                              
                grade TEXT,                                                                                   
                compliance_score REAL,                                                                        
                debt_ratio REAL,                                                                              
                cash_ratio REAL,                                                                              
                tangibility_ratio REAL,                                                                       
                total_haram_ratio REAL,                                                                       
                doubtful_ratio REAL,                                                                          
                total_combined_ratio REAL,                                                                    
                purification_per_share REAL                                                                   
            );                                                                                                
            CREATE TABLE IF NOT EXISTS doubtful_universe (                                                    
                ticker TEXT PRIMARY KEY,                                                                      
                name TEXT,                                                                                    
                sector TEXT,                                                                                  
                industry TEXT,                                                                                
                total_assets REAL,                                                                            
                total_debt REAL,                                                                              
                cash_equivalents REAL,                                                                        
                accounts_receivable REAL,                                                                     
                total_revenue REAL,                                                                           
                interest_income REAL,                                                                         
                shares_outstanding REAL,                                                                      
                avg_market_cap_36mo REAL,                                                                     
                raw_info TEXT,                                                                                
                sec_filing_url TEXT,                                                                          
                fetched_at TEXT,                                                                              
                grade TEXT,                                                                                   
                compliance_score REAL,                                                                        
                debt_ratio REAL,                                                                              
                cash_ratio REAL,                                                                              
                tangibility_ratio REAL,                                                                       
                total_haram_ratio REAL,                                                                       
                doubtful_ratio REAL,                                                                          
                total_combined_ratio REAL,                                                                    
                purification_per_share REAL                                                                   
            );                                                                                                
            CREATE TABLE IF NOT EXISTS halal_rejections (                                                     
                ticker TEXT PRIMARY KEY,                                                                      
                name TEXT,                                                                                    
                sector TEXT,                                                                                  
                industry TEXT,                                                                                
                total_assets REAL,                                                                            
                total_debt REAL,                                                                              
                cash_equivalents REAL,                                                                        
                accounts_receivable REAL,                                                                     
                total_revenue REAL,                                                                           
                interest_income REAL,                                                                         
                shares_outstanding REAL,                                                                      
                avg_market_cap_36mo REAL,                                                                     
                raw_info TEXT,                                                                                
                sec_filing_url TEXT,                                                                          
                fetched_at TEXT,                                                                              
                grade TEXT,
                compliance_score REAL,
                debt_ratio REAL,
                cash_ratio REAL,
                tangibility_ratio REAL,
                total_haram_ratio REAL,
                total_combined_ratio REAL,
                halal_failure TEXT,
                purification_per_share REAL
            );
        """)
    else:
        # B. If we are running in production, create tables via SQLAlchemy models on PostgreSQL                                                                 
        async def _init():                                                                                        
            engine = create_async_engine(ASYNC_DB_URL)                                                            
            async with engine.begin() as conn:                                                                    
                await conn.run_sync(Base.metadata.create_all)                                                     
            await engine.dispose()                                                                                
                                                                                                                
        run_sync(_init())                                                                                         
                                                                                                                
    
    
    # Schema migration: check if stocks table exists and has sec_filing_url column
    table_check = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stocks'").fetchone()
    if table_check:
        cursor = conn.execute("PRAGMA table_info(stocks)")
        columns = [row[1] for row in cursor.fetchall()]
        if "sec_filing_url" not in columns:
            conn.execute("ALTER TABLE stocks ADD COLUMN sec_filing_url TEXT")
            
    # Schema migration for manual_overrides: check if doubtful_revenue_override and is_user_override exist
    mo_check = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='manual_overrides'").fetchone()
    if mo_check:
        cursor = conn.execute("PRAGMA table_info(manual_overrides)")
        columns = [row[1] for row in cursor.fetchall()]
        if "doubtful_revenue_override" not in columns:
            conn.execute("ALTER TABLE manual_overrides ADD COLUMN doubtful_revenue_override REAL")
        if "is_user_override" not in columns:
            conn.execute("ALTER TABLE manual_overrides ADD COLUMN is_user_override INTEGER DEFAULT 0")
        if "tangibility_ratio_override" not in columns:
            conn.execute("ALTER TABLE manual_overrides ADD COLUMN tangibility_ratio_override REAL")

    # Schema migration for other tables to ensure they have tangibility_ratio column
    for table_name in ["halal_universe", "doubtful_universe", "halal_rejections"]:
        t_check = conn.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'").fetchone()
        if t_check:
            cursor = conn.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in cursor.fetchall()]
            if "tangibility_ratio" not in columns:
                conn.execute(f"ALTER TABLE {table_name} ADD COLUMN tangibility_ratio REAL")

    # Create and seed shariah_segment_map
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shariah_segment_map (
            ticker TEXT,
            segment_name TEXT,
            compliance_status TEXT CHECK(compliance_status IN ('halal', 'haram', 'doubtful')),
            notes TEXT,
            PRIMARY KEY (ticker, segment_name)
        )
    """)
    count = conn.execute("SELECT COUNT(*) FROM shariah_segment_map").fetchone()[0]
    if count == 0:
        default_rules = [
            ("ABBV", "Aesthetics", "haram", "Under the Cosmetic Aesthetics Rule, the entire 'Aesthetics' segment (including Botox Cosmetic, Juvederm, and Other Aesthetics) is 100% Haram/non-compliant revenue. Do NOT exclude Botox Cosmetic or Juvederm from the Haram revenue calculation."),
            ("SPCX", "AI", "doubtful", "AI or AI/X segment includes the X platform (social media and digital advertising), Grok, and AI computational infrastructure. Per the Digital Advertising Rule, this segment is classified as Doubtful (5.0% of total revenue if granular data is missing, or the entire segment if reported).")
        ]
        conn.executemany("INSERT INTO shariah_segment_map (ticker, segment_name, compliance_status, notes) VALUES (?, ?, ?, ?)", default_rules)
            
    # Create and seed curated_benchmarks
    conn.execute("""
        CREATE TABLE IF NOT EXISTS curated_benchmarks (
            ticker TEXT PRIMARY KEY,
            haram_revenue_override REAL,
            doubtful_revenue_override REAL,
            interest_income_override REAL,
            cash_ratio_override REAL,
            debt_ratio_override REAL,
            tangibility_ratio_override REAL,
            updated_at TEXT
        )
    """)
    # Check and migrate curated_benchmarks if needed
    cursor_cb = conn.execute("PRAGMA table_info(curated_benchmarks)")
    columns_cb = [row[1] for row in cursor_cb.fetchall()]
    if "tangibility_ratio_override" not in columns_cb:
        conn.execute("ALTER TABLE curated_benchmarks ADD COLUMN tangibility_ratio_override REAL")
    count_cur = conn.execute("SELECT COUNT(*) FROM curated_benchmarks").fetchone()[0]
    if count_cur == 0:
        default_curated = [
            ("MSFT", 0.0760, 0.0, 0.0094, 0.0315, 0.0197, pd.Timestamp.now().isoformat()),
            ("GOOG", 0.0, 0.7200, 0.0108, None, None, pd.Timestamp.now().isoformat()),
            ("GOOGL", 0.0, 0.7200, 0.0108, None, None, pd.Timestamp.now().isoformat()),
            ("META", 0.0, 0.9800, 0.0120, None, None, pd.Timestamp.now().isoformat()),
            ("NVDA", 0.0, 0.0, 0.0106, None, None, pd.Timestamp.now().isoformat()),
            ("AMD", 0.0, 0.0, 0.0062, None, None, pd.Timestamp.now().isoformat()),
            ("QCOM", 0.0, 0.0, 0.0144, None, None, pd.Timestamp.now().isoformat())
        ]
        conn.executemany("""
            INSERT INTO curated_benchmarks 
            (ticker, haram_revenue_override, doubtful_revenue_override, interest_income_override, cash_ratio_override, debt_ratio_override, updated_at) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, default_curated)

    # Create and seed global_segment_patterns
    conn.execute("""
        CREATE TABLE IF NOT EXISTS global_segment_patterns (
            pattern TEXT PRIMARY KEY,
            compliance_status TEXT CHECK(compliance_status IN ('halal', 'haram', 'doubtful')),
            notes TEXT
        )
    """)
    count_pat = conn.execute("SELECT COUNT(*) FROM global_segment_patterns").fetchone()[0]
    if count_pat == 0:
        default_patterns = [
            ("aesthetics", "haram", "Cosmetic Aesthetics Rule (Botox, Juvederm, non-essential cosmetic implants)."),
            ("advertising", "doubtful", "Digital Advertising Rule (unclassified digital ad revenue/ad networks)."),
            ("ad network", "doubtful", "Digital Advertising Rule."),
            ("sponsored search", "doubtful", "Digital Advertising Rule."),
            ("gaming", "doubtful", "General gaming segment without explicit family-friendly classification."),
            ("game content", "doubtful", "Gaming content publisher/distributor."),
            ("interest", "haram", "Conventional financing / conventional interest income."),
            ("credit card", "haram", "Interest-based credit and payment cards."),
            ("lending", "haram", "Interest-bearing consumer or corporate lending."),
            ("casino", "haram", "Gambling and casino operations."),
            ("gambling", "haram", "Sports betting, lotteries, and online gambling."),
            ("tobacco", "haram", "Tobacco manufacturing, distribution, or retail."),
            ("brewery", "haram", "Alcoholic beverages."),
            ("winery", "haram", "Alcoholic beverages."),
            ("distillery", "haram", "Alcoholic beverages."),
            ("pork", "haram", "Pork products manufacturing, distribution, or retail."),
            ("adult", "haram", "Pornography and explicit adult entertainment.")
        ]
        conn.executemany("""
            INSERT INTO global_segment_patterns (pattern, compliance_status, notes)
            VALUES (?, ?, ?)
        """, default_patterns)

    # Create proposed_segment_rules
    conn.execute("""
        CREATE TABLE IF NOT EXISTS proposed_segment_rules (
            ticker TEXT,
            segment_name TEXT,
            compliance_status TEXT CHECK(compliance_status IN ('halal', 'haram', 'doubtful')),
            suggested_notes TEXT,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
            created_at TEXT,
            PRIMARY KEY (ticker, segment_name)
        )
    """)

    conn.commit()
    conn.close()

def save_proposed_rules(ticker, ai_res):
    proposed = ai_res.get("proposed_rules", [])
    if isinstance(proposed, list) and len(proposed) > 0:
        conn = get_db()
        try:
            for rule in proposed:
                seg_name = rule.get("segment_name")
                status = rule.get("compliance_status")
                notes = rule.get("notes")
                if seg_name and status in ["halal", "haram", "doubtful"]:
                    # 1. Save directly to active rules map (auto-approve)
                    conn.execute("""
                        INSERT OR REPLACE INTO shariah_segment_map 
                        (ticker, segment_name, compliance_status, notes)
                        VALUES (?, ?, ?, ?)
                    """, (ticker, seg_name, status, notes))
                    
                    # 2. Record in proposed rules log as approved
                    conn.execute("""
                        INSERT OR REPLACE INTO proposed_segment_rules 
                        (ticker, segment_name, compliance_status, suggested_notes, status, created_at)
                        VALUES (?, ?, ?, ?, 'approved', ?)
                    """, (
                        ticker, 
                        seg_name, 
                        status, 
                        notes, 
                        pd.Timestamp.now().isoformat()
                    ))
            conn.commit()
        except Exception as e:
            print(f"Warning: Could not auto-save segment rules: {e}")
        finally:
            conn.close()
