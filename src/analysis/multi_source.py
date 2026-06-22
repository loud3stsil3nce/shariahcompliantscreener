import os
import json
import datetime
import google.generativeai as genai
_client = genai
from dotenv import load_dotenv

from src.ai.gemini_client import call_gemini
from src.ai.openai_fallback import call_openai
from src.ai.multi_source_prompting import prompt_multi_source, SYSTEM_PROMPT_MULTI_SOURCE
from src.ai.multi_source_schema import MULTI_SOURCE_RESPONSE_SCHEMA

load_dotenv()

# Set up Gemini
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

def write_audit_report(ticker, name, harvested, res):
    """Write a detailed markdown audit report to the logs directory for transparency."""
    os.makedirs("logs", exist_ok=True)
    report_path = f"logs/{ticker.upper()}_multi_source_audit_report.md"
    
    haram_rev_pct = res.get("haram_revenue", 0.0) * 100
    doubtful_rev_pct = res.get("doubtful_revenue", 0.0) * 100
    debt_pct = res.get("interest_bearing_debt", 0.0) * 100
    cash_pct = res.get("interest_bearing_securities", 0.0) * 100
    int_inc_pct = res.get("interest_income", 0.0) * 100
    
    sources_summary = []
    if harvested.get("pdf_url"):
        sources_summary.append(f"- **Investor Presentation PDF**: {harvested.get('pdf_url')}")
    sources_summary.append(f"- **Earnings Call Transcript Available**: {harvested.get('has_transcript')}")
    sources_summary.append(f"- **Web Search Evidence Scraped**: {harvested.get('has_web_search')}")
    
    proposed_rules_str = ""
    for rule in res.get("proposed_rules", []):
        proposed_rules_str += f"| {rule.get('segment_name')} | {rule.get('compliance_status').upper()} | {rule.get('notes')} |\n"
        
    sources_summary_str = "\n".join(sources_summary)
    
    report_content = f"""# Shariah Compliance Audit Report - {ticker.upper()} ({name})
Generated at: {datetime.datetime.now().isoformat()}

## 1. Executive Summary Table
| Metric | Absolute Value (M USD) | Ratio | Denominator Basis |
| :--- | :---: | :---: | :--- |
| **Total Revenue** | ${res.get('total_revenue_millions', 0.0):,.2f}M | 100.00% | Anchor Total Revenue |
| **Haram Business Revenue** | ${res.get('haram_revenue_millions', 0.0):,.2f}M | {haram_rev_pct:.2f}% | Total Revenue |
| **Doubtful Business Revenue** | ${res.get('doubtful_revenue_millions', 0.0):,.2f}M | {doubtful_rev_pct:.2f}% | Total Revenue |
| **Total Debt** | ${res.get('total_debt_millions', 0.0):,.2f}M | 100.00% | Total Debt |
| **Interest-Bearing Debt** | ${res.get('interest_bearing_debt_millions', 0.0):,.2f}M | {debt_pct:.2f}% | Total Debt |
| **Total Cash & Securities** | ${res.get('total_cash_and_securities_millions', 0.0):,.2f}M | 100.00% | Cash Portfolio |
| **Interest-Bearing Securities** | ${res.get('interest_bearing_securities_millions', 0.0):,.2f}M | {cash_pct:.2f}% | Total Cash & Securities |
| **Gross Interest Income** | ${res.get('interest_income_millions', 0.0):,.2f}M | {int_inc_pct:.2f}% | Total Revenue |

## 2. Ingested Data Sources
{sources_summary_str}

## 3. Segment Proposed Rules
| Segment Name | Compliance Grade | Notes |
| :--- | :---: | :--- |
{proposed_rules_str if proposed_rules_str else "| None | - | - |"}

## 4. AI Detailed Reasoning & Citations
{res.get('reasoning', 'No reasoning details provided by the AI.')}
"""
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    print(f"📄 Detailed Shariah audit report written to: {report_path}")

def analyze_multi_source_compliance(ticker, name, harvested, summary=None):
    """
    Perform a robust, multi-source compliance audit on a stock by parsing 
    and reconciling SEC filings, earning transcripts, investor supplements, and search evidence.
    """
    compiled_text = harvested.get("compiled_text", "")
    if not compiled_text:
        return {"error": "Multi-source compiled text is empty or missing."}
        
    conn = None
    db_rules = []
    global_patterns = []
    db_financials = None
    try:
        from src.db.helpers import get_db
        conn = get_db()
        stock = conn.execute("SELECT total_revenue, total_debt, cash_equivalents, interest_income FROM stocks WHERE ticker = ?", (ticker,)).fetchone()
        if stock:
            db_financials = {
                'total_revenue': stock['total_revenue'] or 0.0,
                'total_debt': stock['total_debt'] or 0.0,
                'cash_equivalents': stock['cash_equivalents'] or 0.0,
                'interest_income': stock['interest_income'] or 0.0
            }
        rules_cursor = conn.execute("SELECT segment_name, compliance_status, notes FROM shariah_segment_map WHERE ticker = ?", (ticker,))
        db_rules = rules_cursor.fetchall()
        patterns_cursor = conn.execute("SELECT pattern, compliance_status, notes FROM global_segment_patterns")
        global_patterns = patterns_cursor.fetchall()
    except Exception as e:
        print(f"Error querying database rules in multi_source: {e}")
    finally:
        if conn:
            conn.close()

    db_info = ""
    if db_financials:
        db_info += f"""
        BASELINE FINANCIAL DATA FROM DATABASE (for reference/fallback):
        - Total Revenue: ${db_financials.get('total_revenue', 0.0) / 1e6:,.2f} million
        - Total Debt: ${db_financials.get('total_debt', 0.0) / 1e6:,.2f} million
        - Cash and Equivalents: ${db_financials.get('cash_equivalents', 0.0) / 1e6:,.2f} million
        - Interest Income: ${db_financials.get('interest_income', 0.0) / 1e6:,.2f} million
        """
    
    if db_rules:
        db_info += f"\n        KNOWN COMPANY-SPECIFIC RULES FROM DATABASE FOR {ticker}:\n"
        for rule in db_rules:
            db_info += f"        - Segment: '{rule['segment_name']}' is classified as {rule['compliance_status'].upper()}. Rules/Notes: {rule['notes']}\n"
            
    if global_patterns:
        db_info += "\n        GLOBAL SEGMENT COMPLIANCE PATTERNS:\n"
        for pattern in global_patterns:
            db_info += f"        - Pattern: '{pattern['pattern']}' -> {pattern['compliance_status'].upper()} (Rule: {pattern['notes']})\n"

    prompt_text = prompt_multi_source(name, ticker, summary, compiled_text, db_info=db_info)
    
    # Try Gemini first
    result = call_gemini(prompt_text, SYSTEM_PROMPT_MULTI_SOURCE, client=_client, schema=MULTI_SOURCE_RESPONSE_SCHEMA)
    if isinstance(result, dict) and "error" not in result:
        write_audit_report(ticker, name, harvested, result)
        return result
        
    # Fall back to OpenAI
    result = call_openai(prompt_text, SYSTEM_PROMPT_MULTI_SOURCE, schema=MULTI_SOURCE_RESPONSE_SCHEMA)
    if isinstance(result, dict) and "error" not in result:
        write_audit_report(ticker, name, harvested, result)
        return result
        
    if isinstance(result, dict) and "error" in result:
        return result
        
    return {"error": "All AI services failed during multi-source audit."}
