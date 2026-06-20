RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "haram_revenue": {"type": "number", "description": "Percentage of total revenue from non-compliant segments (0.0 to 1.0)"},
        "doubtful_revenue": {"type": "number", "description": "Percentage of total revenue from questionable/ambiguous/doubtful segments (0.0 to 1.0)"},
        "interest_bearing_debt": {"type": "number", "description": "Percentage of total debt (short-term debt + long-term debt) that is interest-bearing (0.0 to 1.0)"},
        "interest_bearing_securities": {"type": "number", "description": "Percentage of the total cash/equivalents/marketable securities portfolio held in interest-bearing instruments (0.0 to 1.0)"},
        "interest_income": {"type": "number", "description": "Percentage of total revenue from interest (0.0 to 1.0)"},
        
        "total_revenue_millions": {"type": "number", "description": "Total revenue in millions of USD"},
        "haram_revenue_millions": {"type": "number", "description": "Haram/non-compliant revenue in millions of USD"},
        "doubtful_revenue_millions": {"type": "number", "description": "Doubtful/questionable revenue in millions of USD"},
        "total_debt_millions": {"type": "number", "description": "Total debt in millions of USD"},
        "interest_bearing_debt_millions": {"type": "number", "description": "Total interest-bearing debt in millions of USD"},
        "short_term_debt_millions": {"type": "number", "description": "Short-term interest-bearing debt in millions of USD"},
        "long_term_debt_millions": {"type": "number", "description": "Long-term interest-bearing debt in millions of USD"},
        "total_cash_and_securities_millions": {"type": "number", "description": "Total cash and marketable securities portfolio in millions of USD"},
        "interest_bearing_securities_millions": {"type": "number", "description": "Total interest-bearing cash/securities in millions of USD"},
        "short_term_securities_millions": {"type": "number", "description": "Short-term interest-bearing cash/securities in millions of USD"},
        "long_term_securities_millions": {"type": "number", "description": "Long-term interest-bearing securities in millions of USD"},
        "interest_income_millions": {"type": "number", "description": "Gross interest income in millions of USD"},
        
        "reasoning": {"type": "string", "description": "Detailed description of the segment breakdown and specific notes cited"}
    },
    "required": [
        "haram_revenue", "doubtful_revenue", "interest_bearing_debt", "interest_bearing_securities", "interest_income",
        "total_revenue_millions", "haram_revenue_millions", "doubtful_revenue_millions", "total_debt_millions", "interest_bearing_debt_millions",
        "short_term_debt_millions", "long_term_debt_millions",
        "total_cash_and_securities_millions", "interest_bearing_securities_millions",
        "short_term_securities_millions", "long_term_securities_millions",
        "interest_income_millions",
        "reasoning"
    ]
}
