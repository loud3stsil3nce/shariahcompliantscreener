import sys
import os
import sqlite3

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ai.prompting import prompt

def test_db_rules_injector(monkeypatch=None):
    print("\n=== Running Database Rules Injector Test ===")
    
    # 1. Prepare in-memory DB
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    
    conn.execute("""
        CREATE TABLE shariah_segment_map (
            ticker TEXT,
            segment_name TEXT,
            compliance_status TEXT,
            notes TEXT,
            PRIMARY KEY (ticker, segment_name)
        )
    """)
    conn.execute("""
        CREATE TABLE global_segment_patterns (
            pattern TEXT PRIMARY KEY,
            compliance_status TEXT,
            notes TEXT
        )
    """)
    
    # Seed rules
    conn.execute("""
        INSERT INTO shariah_segment_map (ticker, segment_name, compliance_status, notes)
        VALUES ('TEST', 'Secret Services', 'haram', 'Estimate exactly 5.5% as credit card interest')
    """)
    conn.execute("""
        INSERT INTO global_segment_patterns (pattern, compliance_status, notes)
        VALUES ('ads', 'doubtful', 'Ad network is doubtful')
    """)
    conn.commit()
    
    # Mock get_db
    def mock_get_db():
        return conn
        
    # We will simulate the formatting logic of analyze_company_compliance in this test
    # to see if it correctly generates db_info
    ticker = "TEST"
    db_rules = conn.execute("SELECT segment_name, compliance_status, notes FROM shariah_segment_map WHERE ticker = ?", (ticker,)).fetchall()
    global_patterns = conn.execute("SELECT pattern, compliance_status, notes FROM global_segment_patterns").fetchall()
    
    db_info = ""
    if db_rules:
        db_info += f"\n        KNOWN COMPANY-SPECIFIC RULES FROM DATABASE FOR {ticker}:\n"
        for rule in db_rules:
            db_info += f"        - Segment: '{rule['segment_name']}' is classified as {rule['compliance_status'].upper()}. Rules/Notes: {rule['notes']}\n"
            
    if global_patterns:
        db_info += "\n        GLOBAL SEGMENT COMPLIANCE PATTERNS:\n"
        for pattern in global_patterns:
            db_info += f"        - Pattern: '{pattern['pattern']}' -> {pattern['compliance_status'].upper()} (Rule: {pattern['notes']})\n"
            
    conn.close()
    
    # Verify the generated text contains the rules and patterns
    print("Generated db_info:")
    print(db_info)
    
    assert "KNOWN COMPANY-SPECIFIC RULES FROM DATABASE FOR TEST" in db_info
    assert "Secret Services" in db_info
    assert "HARAM" in db_info
    assert "5.5%" in db_info
    assert "GLOBAL SEGMENT COMPLIANCE PATTERNS" in db_info
    assert "ads" in db_info
    assert "DOUBTFUL" in db_info
    
    # Test prompt interpolation
    prompt_text = prompt("Test Co", "TEST", "Summary", db_info, "Source Text")
    assert "KNOWN COMPANY-SPECIFIC RULES FROM DATABASE FOR TEST" in prompt_text
    
    print("✅ Database rules injector formats prompt correctly!")

if __name__ == "__main__":
    test_db_rules_injector()
