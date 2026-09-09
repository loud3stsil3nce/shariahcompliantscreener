import os
import json
import google.generativeai as genai
_client = genai
from dotenv import load_dotenv

from src.ai.gemini_client import call_gemini
from src.ai.openai_fallback import call_openai
from src.ai.prompting import SYSTEM_PROMPT, prompt
from src.analysis.multi_source import analyze_multi_source_compliance

load_dotenv()

# Set up Gemini
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

def analyze_company_compliance(ticker, name, summary, source_text=None, db_financials=None):
    """Orchestrator: try Gemini, fall back to OpenAI."""
    """full Shariah Audit, optionally using 10-K source text."""
  
    conn = None
    db_rules = []
    global_patterns = []
    try:
        from src.db.helpers import get_db
        conn = get_db()
        rules_cursor = conn.execute("SELECT segment_name, compliance_status, notes FROM shariah_segment_map WHERE ticker = ?", (ticker,))
        db_rules = rules_cursor.fetchall()
        patterns_cursor = conn.execute("SELECT pattern, compliance_status, notes FROM global_segment_patterns")
        global_patterns = patterns_cursor.fetchall()
    except Exception as e:
        print(f"Error querying database rules: {e}")
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
    
    prompt_text = prompt(name, ticker, summary, db_info, source_text)
    
    # Try Gemini first
    gemini_result = call_gemini(prompt_text, SYSTEM_PROMPT, client=_client)
    if isinstance(gemini_result, dict) and "error" not in gemini_result:
        return gemini_result
    gemini_err = gemini_result.get("error") if isinstance(gemini_result, dict) else str(gemini_result)
    
    # Fall back to OpenAI - regenerate with smaller source_text to avoid OpenAI TPM limit and context window limits
    openai_prompt_text = prompt(name, ticker, summary, db_info, source_text, max_source_chars=300000)
    openai_result = call_openai(openai_prompt_text, SYSTEM_PROMPT)
    if isinstance(openai_result, dict) and "error" not in openai_result:
        return openai_result
        
    openai_err = openai_result.get("error") if isinstance(openai_result, dict) else str(openai_result)
    return {"error": f"All AI services failed. Gemini: {gemini_err} | OpenAI: {openai_err}"}
