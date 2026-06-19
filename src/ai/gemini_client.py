_client = genai



    """Call Gemini to perform a full Shariah Audit, optionally using 10-K source text."""
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
    
    db_info = ""
    if db_financials:
        db_info = f"""
        BASELINE FINANCIAL DATA FROM DATABASE (for reference/fallback):
        - Total Revenue: ${db_financials.get('total_revenue', 0.0) / 1e6:,.2f} million
        - Total Debt: ${db_financials.get('total_debt', 0.0) / 1e6:,.2f} million
        - Cash and Equivalents: ${db_financials.get('cash_equivalents', 0.0) / 1e6:,.2f} million
        - Interest Income: ${db_financials.get('interest_income', 0.0) / 1e6:,.2f} million
        """

    if source_text:
        prompt = f"""
        Audit this company for Shariah Compliance using the FULL 10-K or 10-Q filing text provided below.
        Name: {name}
        Ticker: {ticker}
        {db_info}
        
        INSTRUCTIONS:
        1. Search the document specifically for "Segment Information" or "Revenue by Product".
        2. Look for tables under "Item 8. Financial Statements" or "Notes to Consolidated Financial Statements".
        3. Extract the DOLLAR AMOUNTS (in millions of USD) for:
           - Non-compliant segments (Music, Video, Gaming, Financial Services).
           - Total Interest-Bearing Debt (notes, term loans, bonds).
           - Marketable Securities (interest-earning).
        4. Populate the absolute values in MILLIONS of USD in the JSON response fields (e.g. total_revenue_millions, haram_revenue_millions, doubtful_revenue_millions, total_debt_millions, interest_bearing_debt_millions, total_cash_and_securities_millions, interest_bearing_securities_millions, interest_income_millions).
        5. Calculate the percentage ratios exactly using these absolute values:
           - "haram_revenue" = "haram_revenue_millions" / "total_revenue_millions"
           - "doubtful_revenue" = "doubtful_revenue_millions" / "total_revenue_millions"
           - "interest_bearing_debt" = "interest_bearing_debt_millions" / "total_debt_millions"
           - "interest_bearing_securities" = "interest_bearing_securities_millions" / "total_cash_and_securities_millions"
           - "interest_income" = "interest_income_millions" / "total_revenue_millions"
           Do NOT copy segment-level sub-percentages (e.g. 5% of Services segment) directly into the total revenue ratio fields. You must always divide the sub-segment dollar amount by the total revenue to calculate the ratio relative to total revenue.
        
        CRITICAL REVENUE SEGMENTATION RULE (Composite Segment Rule - Nuanced Allocation):
        If a large revenue segment (like Apple's "Services" or SpaceX's "AI/xAI") contains both halal and non-compliant or questionable elements, do NOT fail the entire segment and do NOT apply a generic 50% estimate if a more precise disaggregation can be deduced from the filing text.
        Instead:
        - Search the filing text (including Notes to Financial Statements) for sub-product breakdowns.
        - If explicit numbers are available, use them exactly.
        - If explicit numbers are NOT available, make a justified, company-specific estimate based on industry benchmarks:
          - For Apple (AAPL): The Services segment contains Apple Music, Apple TV+, and Apple Card. Estimate that these non-halal/doubtful services represent exactly 13.0% of the Services segment (representing approximately 3.12% of total company revenue). Classify the Apple Card portion (1.5% of the Services segment) as Haram ($915 million for $61B Services) and the remaining mixed streaming/media portion (11.5% of the Services segment) as Doubtful ($7,014 million for $61B Services).
          - For other tech platforms, payment networks, or digital conglomerates: Estimate the non-compliant or questionable sub-products (e.g. music streaming, credit card interest, or digital ads) as representing 5% to 15% of that segment, unless the text provides explicit evidence indicating otherwise.
        - Multiply the segment revenue by the segment-level sub-percentage to get the sub-segment dollar amount.
        - Classify this sub-segment dollar amount correctly:
          - Haram: CLEARLY prohibited sub-elements (conventional interest, credit card interest like Apple Card, mature violent video games, or explicit adult content), adding it to "haram_revenue_millions" and "haram_revenue".
          - Doubtful: AMBIGUOUS, QUESTIONABLE, or MIXED-USE sub-elements (unspecified general media streaming, digital advertising, data licensing, dual-use aerospace connectivity), adding it to "doubtful_revenue_millions" and "doubtful_revenue".
        - Remember: "haram_revenue" and "doubtful_revenue" ratios in the JSON MUST be computed as (sub-segment millions / total_revenue_millions). Do NOT copy segment-level percentages (e.g. 13% of Services segment) directly into the total revenue ratio fields!
        
        CRITICAL VIDEO GAME SEGMENTATION RULE:
        If the company generates revenue from video games or digital gaming, apply the following:
        - Classify as Haram: Mature, adult, or highly violent content (e.g., ESRB M-rated or PEGI 18, like Call of Duty, Diablo, GTA) and monetization mechanics featuring randomized loot boxes or gacha systems. For publishers/segments dominated by these categories (e.g., Microsoft's Xbox/Activision segment, Take-Two Interactive), classify 70% to 100% of the segment revenue as Haram.
        - Classify as Doubtful: Unspecified general gaming revenue or games with moderate fantasy violence but no explicit mature/gambling themes.
        - Classify as Halal: Family-friendly, educational, puzzle, or cognitive games with no mature content or loot boxes.
        
        CRITICAL DIGITAL ADVERTISING RULE:
        If the company generates revenue from digital advertising, search advertising, social media ads, or ad networks (often reported under "Services" or "Advertising"):
        - Classify this advertising revenue as Doubtful. Do NOT classify digital advertising as Halal technology or cloud software, because these ad networks serve a mixture of compliant and non-compliant ads (conventional finance, alcohol, etc.) without detailed splits.
        
        CRITICAL LIQUID ASSETS & CASH SCREEN RULE:
        If the company has a cash, cash equivalents, or short/long-term marketable securities portfolio, classify the ENTIRE liquid cash and securities portfolio (typically 90% to 100% of "total_cash_and_securities_millions") under "interest_bearing_securities_millions". In modern Shariah screening, all marketable investments and bank holdings are grouped as liquid assets for the securities screen. Do NOT subtract cash in bank or Level 1 assets.
        
        CRITICAL GROSS INTEREST INCOME RULE:
        Gross interest income represents yield earned on the cash/securities portfolio. If it is not explicitly isolated on the face of the Income Statement or in the Notes (often consolidated under Net Other Income), do NOT report it as 0.0. Instead, deduce it conservatively by applying an annual yield proxy of 3.0% (e.g. 3.0%) to the "total_cash_and_securities_millions" balance. For example, if cash/investments are $150,000 million, estimate gross interest income as $4,500 million (3.0% yield) and enter this under "interest_income_millions".
        
        DOCUMENT TEXT:
        {source_text[:1500000]}
        
        Return the analysis as a JSON object.
        """
    else:
        prompt = f"""
        Audit this company for Shariah Compliance:
        Name: {name}
        Ticker: {ticker}
        Summary: {summary}
        {db_info}
        
        INSTRUCTIONS:
        1. Use the baseline financial data provided to estimate the absolute millions of USD fields.
        2. Populate the absolute values in MILLIONS of USD in the JSON response fields (e.g. total_revenue_millions, haram_revenue_millions, doubtful_revenue_millions, total_debt_millions, interest_bearing_debt_millions, total_cash_and_securities_millions, interest_bearing_securities_millions, interest_income_millions).
        3. Calculate the percentage ratios exactly using these absolute values:
           - "haram_revenue" = "haram_revenue_millions" / "total_revenue_millions"
           - "doubtful_revenue" = "doubtful_revenue_millions" / "total_revenue_millions"
           - "interest_bearing_debt" = "interest_bearing_debt_millions" / "total_debt_millions"
           - "interest_bearing_securities" = "interest_bearing_securities_millions" / "total_cash_and_securities_millions"
           - "interest_income" = "interest_income_millions" / "total_revenue_millions"
           Do NOT copy segment-level sub-percentages (e.g. 5% of Services segment) directly into the total revenue ratio fields. You must always divide the sub-segment dollar amount by the total revenue to calculate the ratio relative to total revenue.
        
        CRITICAL REVENUE SEGMENTATION RULE (Composite Segment Rule - Nuanced Allocation):
        If the company has a mixed segment like "Services" or "AI", do NOT apply a generic 50% estimate.
        Instead, estimate a justified, company-specific percentage of that segment representing only the active non-compliant or questionable sub-products (such as music streaming, credit card interest, or digital ads):
        - For Apple (AAPL): The Services segment contains Apple Music, Apple TV+, and Apple Card. Estimate that these non-halal/doubtful services represent exactly 13.0% of the Services segment (representing approximately 3.12% of total company revenue). Classify the Apple Card portion (1.5% of the Services segment) as Haram ($915 million for $61B Services) and the remaining mixed streaming/media portion (11.5% of the Services segment) as Doubtful ($7,014 million for $61B Services).
        - For other tech platforms, payment networks, or digital conglomerates: Estimate the non-compliant or questionable sub-products (e.g. music streaming, credit card interest, or digital ads) as representing 5% to 15% of that segment, unless the text provides explicit evidence indicating otherwise.
        - Classify this sub-segment dollar amount correctly:
          - Haram: CLEARLY prohibited sub-elements (conventional interest, credit card interest like Apple Card, mature violent video games, or explicit adult content), adding it to "haram_revenue_millions" and "haram_revenue".
          - Doubtful: AMBIGUOUS, QUESTIONABLE, or MIXED-USE sub-elements (unspecified general media streaming, digital advertising, data licensing, dual-use aerospace connectivity), adding it to "doubtful_revenue_millions" and "doubtful_revenue".
        - Remember: "haram_revenue" and "doubtful_revenue" ratios in the JSON MUST be computed as (sub-segment millions / total_revenue_millions). Do NOT copy segment-level percentages (e.g. 13% of Services segment) directly into the total revenue ratio fields!
        
        CRITICAL VIDEO GAME SEGMENTATION RULE:
        For video game or digital gaming revenue, classify:
        - Haram: Mature, violent, or adult content (e.g., ESRB M-rated/PEGI 18 like Call of Duty, Diablo, GTA) and gacha/loot box mechanics. Classify 70% to 100% of gaming segments dominated by these as Haram (e.g., Microsoft's Xbox/Activision Blizzard segment).
        - Doubtful: Unspecified general video games or mixed-portfolio gaming with moderate fantasy violence.
        - Halal: Family-friendly, educational, or puzzle games without mature content or loot boxes.
        
        CRITICAL DIGITAL ADVERTISING RULE:
        For digital advertising, search ads, social media ads, or ad network revenue (often reported under "Services" or "Advertising"):
        - Classify this advertising revenue as Doubtful. Do NOT classify digital advertising as Halal technology or cloud software, because these ad networks serve a mixture of compliant and non-compliant ads (conventional finance, alcohol, etc.) without detailed splits.
        
        CRITICAL LIQUID ASSETS & CASH SCREEN RULE:
        If the company has a cash, cash equivalents, or short/long-term marketable securities portfolio, classify the ENTIRE liquid cash and securities portfolio (typically 90% to 100% of "total_cash_and_securities_millions") under "interest_bearing_securities_millions". In modern Shariah screening, all marketable investments and bank holdings are grouped as liquid assets for the securities screen. Do NOT subtract cash in bank or Level 1 assets.
        
        CRITICAL GROSS INTEREST INCOME RULE:
        Gross interest income represents yield earned on the cash/securities portfolio. If it is not explicitly isolated on the face of the Income Statement or in the Notes (often consolidated under Net Other Income), do NOT report it as 0.0. Instead, deduce it conservatively by applying an annual yield proxy of 3.0% (e.g. 3.0%) to the "total_cash_and_securities_millions" balance. For example, if cash/investments are $150,000 million, estimate gross interest income as $4,500 million (3.0% yield) and enter this under "interest_income_millions".
        
        Return the analysis as a JSON object.
        """
        
    import time
    import re

    last_error = ""
    for model_name in models_to_try:
        for attempt in range(3):
            try:
                # temporary comment out to see effects of change to _client
                #model = genai.GenerativeModel(
                #    model_name=model_name,
                #    system_instruction=SYSTEM_PROMPT
                #)
                response = _client.models.generate_content(
                    model=model_name,
                    prompt=prompt,
                    system_instruction=SYSTEM_PROMPT,
                    generation_config=genai.types.GenerationConfig(
                        response_mime_type="application/json",
                        response_schema=RESPONSE_SCHEMA 
                    )
                )
                return json.loads(response.text)
            except Exception as e:
                err_str = str(e)
                last_error = err_str
                
                # Check if it is a rate limit or quota exceeded error
                if "429" in err_str or "quota" in err_str.lower() or "limit" in err_str.lower():
                    # Check if it is a transient RPM/TPM limit or a daily limit
                    is_daily = "daily" in err_str.lower() or "perday" in err_str.lower()
                    
                    if not is_daily and attempt < 2:
                        # Find sleep delay from API message
                        sleep_time = 10.0  # default backoff
                        match = re.search(r"retry in (\d+\.?\d*)s", err_str)
                        if match:
                            sleep_time = float(match.group(1)) + 1.0
                        else:
                            # Try to match retry_delay { seconds: 30 } format
                            match_delay = re.search(r"retry_delay\s*{\s*seconds:\s*(\d+)\s*}", err_str)
                            if match_delay:
                                sleep_time = float(match_delay.group(1)) + 1.0
                                
                        print(f"⚠️ Warning: Model {model_name} hit transient rate limit. Sleeping {sleep_time:.2f}s before retry (attempt {attempt+1}/3)...")
                        time.sleep(sleep_time)
                        continue
                    else:
                        print(f"⚠️ Warning: Model {model_name} failed with daily/final quota error. Falling back to next model...")
                        break  # Break out of attempts loop to try next model in the chain
                else:
                    return {"error": f"AI Analysis failed on {model_name}: {err_str}"}
     
     
     
     