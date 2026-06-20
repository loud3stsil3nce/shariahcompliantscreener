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
  
    db_info = ""
    if db_financials:
        db_info = f"""
        BASELINE FINANCIAL DATA FROM DATABASE (for reference/fallback):
        - Total Revenue: ${db_financials.get('total_revenue', 0.0) / 1e6:,.2f} million
        - Total Debt: ${db_financials.get('total_debt', 0.0) / 1e6:,.2f} million
        - Cash and Equivalents: ${db_financials.get('cash_equivalents', 0.0) / 1e6:,.2f} million
        - Interest Income: ${db_financials.get('interest_income', 0.0) / 1e6:,.2f} million
        """
    
    prompt_text = prompt(name, ticker, summary, db_info, source_text)
    
    # Try Gemini first
    result = call_gemini(prompt_text, SYSTEM_PROMPT, client=_client)
    if isinstance(result, dict) and "error" not in result:
        return result
    
    # Fall back to OpenAI
    result = call_openai(prompt_text, SYSTEM_PROMPT)
    if isinstance(result, dict) and "error" not in result:
        return result
        
    if isinstance(result, dict) and "error" in result:
        return result
    return {"error": "All AI services failed. Models exceeded quota/limits"}
