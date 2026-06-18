import sqlite3
import pytest
import pandas as pd
from src.db_setup import save_proposed_rules
from src.utils import get_db

def test_save_proposed_rules(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    
    # Create shariah_segment_map
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shariah_segment_map (
            ticker TEXT,
            segment_name TEXT,
            compliance_status TEXT CHECK(compliance_status IN ('halal', 'haram', 'doubtful')),
            notes TEXT,
            PRIMARY KEY (ticker, segment_name)
        )
    """)
    
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

    def fake_get_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr("src.db_setup.get_db", fake_get_db)

    ai_res = {
        "proposed_rules": [
            {
                "segment_name": "Test Segment",
                "compliance_status": "doubtful",
                "notes": "Testing proposed rule saving"
            }
        ]
    }

    save_proposed_rules("TEST", ai_res)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Assert proposed_segment_rules log entry
    cursor.execute("SELECT * FROM proposed_segment_rules")
    prop_rows = cursor.fetchall()
    assert len(prop_rows) == 1
    assert prop_rows[0][0] == "TEST"
    assert prop_rows[0][1] == "Test Segment"
    assert prop_rows[0][2] == "doubtful"
    assert prop_rows[0][3] == "Testing proposed rule saving"
    assert prop_rows[0][4] == "approved"  # Should be automatically approved!
    
    # Assert active shariah_segment_map entry
    cursor.execute("SELECT * FROM shariah_segment_map")
    map_rows = cursor.fetchall()
    assert len(map_rows) == 1
    assert map_rows[0][0] == "TEST"
    assert map_rows[0][1] == "Test Segment"
    assert map_rows[0][2] == "doubtful"
    assert map_rows[0][3] == "Testing proposed rule saving"
    
    conn.close()
