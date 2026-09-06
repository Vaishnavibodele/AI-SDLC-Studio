import re
import json
from ..services.llm_provider import get_llm, get_content_text

def detect_prompt_injection(text: str) -> bool:
    """
    Scans the text for common prompt injection patterns using regex.
    Returns True if an injection attempt is detected.
    """
    patterns = [
        r"ignore\s+(?:all\s+)?previous\s+instructions",
        r"disregard\s+(?:all\s+)?prior\s+prompts",
        r"you\s+are\s+now\s+a\s+different\s+agent",
        r"override\s+system\s+instructions",
        r"forget\s+what\s+you\s+were\s+told",
        r"instead\s+of\s+following\s+rules",
        r"bypass\s+restrictions",
        r"ignore\s+above\s+and\s+do",
        r"ignore\s+below\s+and\s+do",
        r"system\s+override",
        r"developer\s+mode\s+enable",
        r"act\s+as\s+an\s+unrestricted",
        r"jailbreak",
        r"do\s+anything\s+now",
        r"dan\s+mode",
    ]
    
    text_lower = text.lower()
    for pattern in patterns:
        if re.search(pattern, text_lower):
            return True
            
    return False

def check_relevance(text: str) -> bool:
    """
    Queries LLM to classify if the request is relevant to software development.
    Returns True if relevant, False otherwise.
    """
    if not text.strip():
        return False
        
    llm = get_llm()
    system_prompt = (
        "You are a Software Development Assistant. Your task is to analyze if a user request "
        "is related to software development, application design, system architecture, database design, "
        "APIs, websites, code synthesis, business analysis for software, or SDLC processes.\n"
        "Return ONLY a raw JSON object with the format: {\"relevant\": true/false, \"reason\": \"explanation\"}\n"
        "Do not include any markdown backticks or other text."
    )
    
    try:
        response = llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Analyze the following user input:\n\n{text}"}
        ])
        
        content = get_content_text(response).strip()
        # strip markdown if LLM returned it
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        result = json.loads(content)
        return bool(result.get("relevant", False))
    except Exception as e:
        print(f"[Guardrails] Error in check_relevance: {e}")
        # Default to True on error to avoid blocking valid requests on LLM blips
        return True
