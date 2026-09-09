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



def call_gemini(prompt_text,system_prompt, client=None, schema=None):
    """Call Gemini to perform a full Shariah Audit, optionally using 10-K source text."""
    client = client or genai
    schema = schema or RESPONSE_SCHEMA
    passed_client = client

    active_key = os.getenv('GEMINI_API_KEY') or api_key

    if not active_key and passed_client is None:

        return {'error': 'Gemini API Key not found.'}

    # Fallback chain prioritizing active Gemini models
    models_to_try = [
        'models/gemini-3.6-flash',
        'models/gemini-flash-latest',
        'models/gemini-flash-lite-latest',
        'models/gemini-pro-latest'
    ]
    
    last_error = None
    for model_name in models_to_try:
        for attempt in range(3):
            try:
                if hasattr(client, "models") and hasattr(client.models, "generate_content"):
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt_text,
                        config=genai.types.GenerationConfig(
                            response_mime_type="application/json",
                            response_schema=schema,
                            temperature=0.1
                        )
                    )
                else:
                    model = client.GenerativeModel(
                        model_name=model_name,
                        system_instruction=system_prompt
                    )
                    response = model.generate_content(
                        prompt_text,
                        generation_config=genai.types.GenerationConfig(
                            response_mime_type="application/json",
                            response_schema=schema,
                            temperature=0.1
                        )
                    )
                return json.loads(response.text)
            except Exception as e:
                err_str = str(e)
                last_error = err_str
                if "429" in err_str or "quota" in err_str.lower() or "limit" in err_str.lower():
                    fallback_on_rate_limit = os.getenv("FALLBACK_ON_RATE_LIMIT", "true").lower() in ("true", "1", "yes")
                    if fallback_on_rate_limit:
                        print(f"⚠️ Warning: Model {model_name} hit rate limit. Switching to fallback service immediately.")
                        return {"error": f"Gemini rate limit hit: {err_str}"}

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
                elif "404" in err_str or "not found" in err_str.lower():
                    print(f"⚠️ Warning: Model {model_name} not found (404). Trying next model...")
                    break
                else:
                    print(f"⚠️ Warning: Model {model_name} failed: {err_str}. Trying next model...")
                    break
    return {"error": f"All Gemini models failed: {last_error}"}
