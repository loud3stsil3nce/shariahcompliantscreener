import os
import json
import requests
from dotenv import load_dotenv
from src.ai.schema import RESPONSE_SCHEMA

load_dotenv()



def call_openai(prompt_text, system_prompt):
    """OpenAI fallback when Gemini fails."""
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        return None
    
    print("⚠️ Attempting OpenAI (gpt-4o-mini) fallback...")
    headers = {
        "Authorization": f"Bearer {openai_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt_text}
        ],
        "functions": [
            {"name": "audit", "description": "Return compliance audit", "parameters": RESPONSE_SCHEMA}
        ],
        "function_call": {"name": "audit"},
        "temperature": 0.1
    }
    try:
        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=90)
        r.raise_for_status()
        res_json = r.json()
        msg = res_json["choices"][0]["message"]
        
        if "function_call" in msg:
            parsed = json.loads(msg["function_call"].get("arguments", "{}"))
        else:
            parsed = json.loads(msg.get("content", "{}"))
        
        for k in RESPONSE_SCHEMA.get("required", []):
            if k not in parsed:
                raise ValueError(f"Missing required key: {k}")
        
        parsed["audit_source"] = "OpenAI Fallback (gpt-4o-mini)"
        return parsed
    except Exception as e:
        return {"error": f"OpenAI fallback failed: {e}"}