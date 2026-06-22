import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ai.prompting import SYSTEM_PROMPT, PROMPT_WITH_SOURCE, PROMPT_WITHOUT_SOURCE
from src.ai.multi_source_prompting import SYSTEM_PROMPT_MULTI_SOURCE, PROMPT_MULTI_SOURCE

def test_prompt_cleanliness():
    forbidden_terms = [
        "AAPL", "Apple", "SpaceX", "SPCX", "1.5%", "11.5%", "13.0%", "13%", "3.12%", "2.19%", "0.83%", "0.09%"
    ]
    
    prompts_to_check = {
        "SYSTEM_PROMPT": SYSTEM_PROMPT,
        "PROMPT_WITH_SOURCE": PROMPT_WITH_SOURCE,
        "PROMPT_WITHOUT_SOURCE": PROMPT_WITHOUT_SOURCE,
        "SYSTEM_PROMPT_MULTI_SOURCE": SYSTEM_PROMPT_MULTI_SOURCE,
        "PROMPT_MULTI_SOURCE": PROMPT_MULTI_SOURCE
    }
    
    print("\n=== Running Prompt Cleanliness Check ===")
    errors = 0
    for name, content in prompts_to_check.items():
        print(f"Checking {name}...")
        for term in forbidden_terms:
            if term.lower() in content.lower():
                print(f"❌ Error: Forbidden term '{term}' found in {name}!")
                errors += 1
                
    if errors == 0:
        print("✅ All prompt templates are completely clean of hardcoded stock references!")
        sys.exit(0)
    else:
        print(f"❌ Failed cleanliness check with {errors} violations.")
        sys.exit(1)

if __name__ == "__main__":
    test_prompt_cleanliness()
