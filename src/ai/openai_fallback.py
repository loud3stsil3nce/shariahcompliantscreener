openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        print("⚠️ All Gemini models exceeded quota/limits. Attempting OpenAI (gpt-4o-mini) fallback...")
        import requests
        headers = {
            "Authorization": f"Bearer {openai_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
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
                args = msg["function_call"].get("arguments", "{}")
                parsed = json.loads(args)
            else:
                content = msg.get("content", "")
                parsed = json.loads(content) if content else {}

            # simple validation
            for k in RESPONSE_SCHEMA.get("required", []):
                if k not in parsed:
                    raise ValueError(f"Missing required key: {k}")

            parsed["audit_source"] = "OpenAI Fallback (gpt-4o-mini)"
            return parsed
        except Exception as e:
            last_error += f" | OpenAI fallback failed: {e}"