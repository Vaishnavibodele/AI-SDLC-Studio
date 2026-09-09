"""UI executor using Selenium when sufficient UI instructions exist.

Requirements for execution:
- `ui_actions` key present with a list of actions (dicts) describing interactions
  (e.g., {"action": "open", "url": "https://..."}, {"action": "click", "selector": "#id"}).
- If Selenium is unavailable or actions missing, return SKIPPED.
"""

from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

# Ensure these symbols exist at module level so tests can monkeypatch them
webdriver = None
By = None
WebDriverWait = None
EC = None

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    HAS_SELENIUM = True
except Exception:
    HAS_SELENIUM = False


def run(test_case: Dict[str, Any]) -> Dict[str, Any]:
    if not HAS_SELENIUM:
        return {"status": "SKIPPED", "details": "selenium not installed"}

    actions = test_case.get("ui_actions")
    if not actions or not isinstance(actions, list):
        return {"status": "SKIPPED", "details": "No UI actions provided"}

    # For safety, use headless Chrome if possible
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        driver = webdriver.Chrome(options=options)
    except Exception as e:
        logger.exception("Failed to start WebDriver")
        return {"status": "ERROR", "details": f"WebDriver startup failed: {e}"}

    try:
        for act in actions:
            a = act.get("action")
            if a == "open":
                url = act.get("url")
                driver.get(url)
            elif a == "click":
                sel = act.get("selector")
                el = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
                el.click()
            elif a == "wait":
                sel = act.get("selector")
                WebDriverWait(driver, act.get("timeout", 10)).until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
            elif a == "input":
                sel = act.get("selector")
                val = act.get("value", "")
                el = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
                el.clear()
                el.send_keys(val)
            else:
                # Unknown action
                continue

        return {"status": "PASS", "details": "UI interactions completed"}
    except Exception as e:
        logger.exception("UI action failed")
        return {"status": "ERROR", "details": str(e)}
    finally:
        try:
            driver.quit()
        except Exception:
            pass
