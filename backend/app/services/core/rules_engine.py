import re
from typing import List, Dict, Any

class RulesEngine:
    def __init__(self):
        # Security constraints and style constraints
        self.rules = [
            {
                "id": "RULE-SEC-001",
                "name": "SQL Injection Check",
                "description": "Ensure no direct raw string interpolation is used for queries",
                "severity": "CRITICAL",
                "checker": self.check_sql_injection
            },
            {
                "id": "RULE-STYLE-002",
                "name": "PEP-8 Style Check",
                "description": "Verify formatting has no obvious indentation issues",
                "severity": "WARNING",
                "checker": self.check_formatting
            },
            {
                "id": "RULE-SEC-003",
                "name": "Hardcoded Credentials",
                "description": "Ensure no passwords, tokens or secret credentials are plain in variables",
                "severity": "CRITICAL",
                "checker": self.check_credentials
            }
        ]

    def check_sql_injection(self, path: str, content: str) -> List[str]:
        errors = []
        if path.endswith(".py"):
            # Check if executing string concatenation like execute("SELECT ... " + var)
            matches = re.findall(r'\.execute\([\'"][^\'"]*%\s*\w+|\.execute\([\'"][^\'"]*\{\}\'\.format|\.execute\(f[\'"][^\'"]*\{\w+\}', content)
            if matches:
                errors.append(f"SQL Injection Vulnerability: direct parameter formatting found in {path}")
        return errors

    def check_formatting(self, path: str, content: str) -> List[str]:
        warnings = []
        if path.endswith(".py"):
            # Check tabs vs spaces
            if "\t" in content:
                warnings.append(f"PEP-8 Warning: Tabs found in {path}. Clean coding guidelines mandate 4-space indentations.")
        return warnings

    def check_credentials(self, path: str, content: str) -> List[str]:
        errors = []
        # Check variable assignment for generic secrets
        secret_patterns = [
            r'password\s*=\s*[\'"][^\'"]+[\'"]',
            r'secret_key\s*=\s*[\'"][^\'"]+[\'"]',
            r'api_key\s*=\s*[\'"][^\'"]+[\'"]'
        ]
        for pattern in secret_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            # Exclude default placeholders
            for m in matches:
                if "placeholder" not in m.lower() and "secret_key_jwt" not in m.lower():
                    errors.append(f"Security Alert: Hardcoded credentials or raw keys assignment detected in {path}: {m}")
        return errors

    def validate_file(self, path: str, content: str) -> List[Dict[str, Any]]:
        reports = []
        for r in self.rules:
            issues = r["checker"](path, content)
            for issue in issues:
                reports.append({
                    "rule_id": r["id"],
                    "name": r["name"],
                    "severity": r["severity"],
                    "issue": issue
                })
        return reports

rules_engine = RulesEngine()
