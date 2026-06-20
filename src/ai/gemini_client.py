import os
import json
import time
import re
import google.generativeai as genai
from dotenv import load_dotenv
from src.ai.schema import RESPONSE_SCHEMA

_client = genai

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)



def call_gemini(prompt_text,system_prompt, client=None):
    """Call Gemini to perform a full Shariah Audit, optionally using 10-K source text."""
    client = client or genai
    if not api_key:
        return {"error": "Gemini API Key not found."}

    # Fallback chain optimized for user rate limits (prioritizing 500 RPD 3.1 Flash Lite)
    models_to_try = [
        'models/gemini-3.1-flash-lite',
        'models/gemini-3.5-flash',
        'models/gemini-2.5-flash',
        'models/gemini-2.0-flash-lite',
        'models/gemini-2.0-flash',
        'models/gemini-flash-latest',
        'models/gemini-2.5-pro'
    ]
    
    for model_name in models_to_try:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    prompt=prompt_text,
                    system_instruction=system_prompt,
                    generation_config=genai.types.GenerationConfig(
                        response_mime_type="application/json",
                        response_schema=RESPONSE_SCHEMA 
                    )
                )
                return json.loads(response.text)
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "quota" in err_str.lower() or "limit" in err_str.lower():
                    is_daily = "daily" in err_str.lower() or "perday" in err_str.lower()
                    if not is_daily and attempt < 2:
                        sleep_time = 10.0
                        match = re.search(r"retry in (\d+\.?\d*)s", err_str)
                        if match:
                            sleep_time = float(match.group(1)) + 1.0
                        print(f"⚠️ Warning: Model {model_name} hit rate limit. Sleeping {sleep_time:.2f}s...")
                        time.sleep(sleep_time)
                        continue
                    else:
                        print(f"⚠️ Warning: Model {model_name} daily quota exceeded. Trying next...")
                        break
                else:
                    return {"error": f"Gemini failed: {err_str}"}
    return {"error": "All Gemini models failed"}
     
     
     