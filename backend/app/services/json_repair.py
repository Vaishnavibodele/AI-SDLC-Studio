import re
import json
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from ..services import project_service
from ..services.llm_provider import get_llm, get_content_text

def attempt_regex_repair(raw_str: str) -> str:
    """
    Applies regex-based rules to fix common JSON malformations.
    """
    repaired = get_content_text(raw_str).strip()
    
    # Strip markdown block ticks if any
    if repaired.startswith("```json"):
        repaired = repaired[7:]
    if repaired.startswith("```"):
        repaired = repaired[3:]
    if repaired.endswith("```"):
        repaired = repaired[:-3]
    repaired = repaired.strip()
    
    # Remove trailing commas in objects and arrays
    repaired = re.sub(r',\s*\}', '}', repaired)
    repaired = re.sub(r',\s*\]', ']', repaired)
    
    # Try to balance unclosed brackets
    # Count braces
    open_braces = repaired.count('{')
    close_braces = repaired.count('}')
    if open_braces > close_braces:
        repaired += '}' * (open_braces - close_braces)
        
    open_brackets = repaired.count('[')
    close_brackets = repaired.count(']')
    if open_brackets > close_brackets:
        repaired += ']' * (open_brackets - close_brackets)
        
    return repaired

def repair_json(
    raw_str: Any,
    db: Optional[Session] = None,
    project_id: Optional[str] = None,
    llm_fallback: bool = True
) -> Dict[str, Any]:
    """
    Attempts to parse a JSON string. If parsing fails, applies syntax repairs,
    optionally calling the LLM to fix it.
    """
    raw_str = get_content_text(raw_str)
    # 1. Direct parse attempt
    try:
        data = json.loads(raw_str.strip())
        if not data and len(raw_str.strip()) > 10:
            raise ValueError("Parsed JSON resulted in an empty object from substantial input.")
        return data
    except Exception as e:
        original_error = str(e)
        log_msg = f"Initial JSON parse failed: {original_error}. Attempting regex repairs..."
        print(f"[JSON Repair] {log_msg}")
        if db and project_id:
            project_service.log_activity(db, project_id, "JSON_REPAIR_START", log_msg[:200])

    # 2. Regex-based repair attempt
    repaired_str = attempt_regex_repair(raw_str)
    try:
        data = json.loads(repaired_str)
        # Ensure we didn't just truncate to an empty structure
        if not data and len(raw_str.strip()) > 10:
            raise ValueError("Regex repair succeeded technically but resulted in an empty structure.")
        
        log_msg = "JSON repaired successfully using regex-based cleaning rules."
        print(f"[JSON Repair] {log_msg}")
        if db and project_id:
            project_service.log_activity(db, project_id, "JSON_REPAIR_REGEX_SUCCESS", log_msg)
        return data
    except Exception as e:
        regex_error = str(e)
        log_msg = f"Regex-based JSON repair failed: {regex_error}."
        print(f"[JSON Repair] {log_msg}")
        if db and project_id:
            project_service.log_activity(db, project_id, "JSON_REPAIR_REGEX_FAILED", log_msg[:200])

    # 3. LLM-based repair fallback
    if llm_fallback:
        log_msg = "Attempting LLM-based JSON repair..."
        print(f"[JSON Repair] {log_msg}")
        if db and project_id:
            project_service.log_activity(db, project_id, "JSON_REPAIR_LLM_START", log_msg)
            
        llm = get_llm()
        system_prompt = (
            "You are a JSON repair utility. You will receive a malformed JSON string that failed validation, "
            "along with the parsing error. Your job is to return the fixed, valid JSON string and nothing else.\n"
            "Do not include any chat formatting, markdown blocks, backticks, or preamble. Return ONLY the raw valid JSON.\n"
            "If the text is unrecoverable, return an empty JSON object {}."
        )
        
        user_prompt = (
            f"Error: {original_error}\n"
            f"Malformed JSON:\n{raw_str}"
        )
        
        try:
            response = llm.invoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ])
            
            repaired_content = get_content_text(response).strip()
            if repaired_content.startswith("```json"):
                repaired_content = repaired_content[7:]
            if repaired_content.startswith("```"):
                repaired_content = repaired_content[3:]
            if repaired_content.endswith("```"):
                repaired_content = repaired_content[:-3]
            repaired_content = repaired_content.strip()
            
            data = json.loads(repaired_content)
            
            # Guardrail check: did it just return empty or placeholder?
            if not data and len(raw_str.strip()) > 10:
                raise ValueError("LLM returned an empty object, losing original information.")
                
            log_msg = "JSON repaired successfully using LLM repair step."
            print(f"[JSON Repair] {log_msg}")
            if db and project_id:
                project_service.log_activity(db, project_id, "JSON_REPAIR_LLM_SUCCESS", log_msg)
            return data
        except Exception as e:
            log_msg = f"LLM JSON repair failed: {str(e)}"
            print(f"[JSON Repair] {log_msg}")
            if db and project_id:
                project_service.log_activity(db, project_id, "JSON_REPAIR_LLM_FAILED", log_msg[:200])
                
    # If all repairs fail, raise final exception to prompt re-generation or agent retry
    raise ValueError(f"Failed to parse and repair JSON. Original error: {original_error}")
