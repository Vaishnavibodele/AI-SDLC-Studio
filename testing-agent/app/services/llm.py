import os
import logging
from typing import Type, TypeVar, Optional, List
from pydantic import BaseModel, Field

# Import schemas to compile responses and mock structures
from app.models.state import (
    RequirementInfo,
    RiskInfo,
    ChangeImpactInfo,
    CoverageInfo,
    TestStrategyInfo,
    TestCaseInfo,
    TestScenarioInfo,
    GeneratedTestDataInfo,
)

logger = logging.getLogger(__name__)

# generic model type parameter for schema validation
T = TypeVar("T", bound=BaseModel)

# Define wrappers for list responses required by structured output generation APIs
class RequirementsWrapper(BaseModel):
    requirements: List[RequirementInfo] = Field(..., description="List of extracted testable requirements")

class RisksWrapper(BaseModel):
    risks: List[RiskInfo] = Field(..., description="List of identified software and design risks")

class TestCasesWrapper(BaseModel):
    __test__ = False
    test_cases: List[TestCaseInfo] = Field(..., description="List of structured test case specifications")

class NegativeBoundaryTestCasesWrapper(BaseModel):
    __test__ = False
    test_cases: List[TestCaseInfo] = Field(..., description="List of negative/boundary/edge test case specifications")

class TestScenariosWrapper(BaseModel):
    __test__ = False
    test_scenarios: List[TestScenarioInfo] = Field(..., description="List of business test scenarios")

class TestDataWrapper(BaseModel):
    __test__ = False
    generated_test_data: List[GeneratedTestDataInfo] = Field(..., description="List of generated test data records")

class GeminiService:
    """
    Service layer providing unified access to Gemini LLM with Pydantic validation
    and deterministic mock fallbacks depending on execution mode.
    """
    def __init__(self):
        # LLM_MODE can be 'mock' or 'gemini'
        self.llm_mode = os.getenv("LLM_MODE", "mock").lower()
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.client = None

        logger.info(f"Initializing GeminiService in '{self.llm_mode}' mode.")

        if self.llm_mode == "gemini":
            if not self.api_key:
                raise ValueError(
                    "GEMINI_API_KEY environment variable is missing, "
                    "but LLM_MODE is configured as 'gemini'. Real execution requires an API key."
                )
            
            # Late import of google-genai to avoid import issues in non-genai configurations
            from google import genai
            self.client = genai.Client(api_key=self.api_key)

    def generate_structured_output(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str] = None
    ) -> T:
        """
        Requests structured output from Gemini using Pydantic schema validation.
        In mock mode, returns pre-defined high-fidelity mock models.
        """
        if self.llm_mode == "mock":
            return self._generate_mock_output(response_schema)

        if not self.client:
            raise RuntimeError("Gemini SDK client was not initialized properly.")

        try:
            from google.genai import types
            
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_schema,
                system_instruction=system_instruction,
                temperature=0.1,  # Lower temperature for deterministic reasoning/extraction
            )

            logger.info(f"Requesting Gemini API structured content for {response_schema.__name__}")
            
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=config
            )

            if not response.text:
                raise ValueError("Gemini returned an empty/null response text.")

            # Validate response string against Pydantic schema
            validated_object = response_schema.model_validate_json(response.text)
            return validated_object

        except Exception as e:
            logger.error(f"Gemini Structured generation failed: {str(e)}", exc_info=True)
            raise RuntimeError(f"Failed to generate structured AI analysis: {str(e)}")

    def _generate_mock_output(self, response_schema: Type[T]) -> T:
        """
        Creates rich, deterministic mock data matching target schemas for offline testing.
        """
        schema_name = response_schema.__name__
        logger.info(f"Generating offline mock for Pydantic schema: {schema_name}")

        if response_schema is RequirementsWrapper:
            data = {
                "requirements": [
                    {
                        "id": "REQ-001",
                        "description": "The system must process real-time room temperature and telemetry readings.",
                        "category": "Functional",
                        "source": "srs"
                    },
                    {
                        "id": "REQ-002",
                        "description": "Trigger automated alerts when device readings exceed configurable thresholds.",
                        "category": "Functional",
                        "source": "srs"
                    },
                    {
                        "id": "REQ-003",
                        "description": "State telemetry collector must be isolated as an independent microservice.",
                        "category": "Functional",
                        "source": "sdd"
                    }
                ]
            }
            return response_schema.model_validate(data)

        elif response_schema is RisksWrapper:
            data = {
                "risks": [
                    {
                        "risk_id": "RSK-001",
                        "requirement_id": "REQ-001",
                        "description": "High frequency data bursts from sensor devices may overflow DB buffer size.",
                        "severity": "Medium",
                        "likelihood": "Low",
                        "mitigation": "Write high-load mock telemetries to verify buffer queue overflows.",
                        "source": "ai_inference"
                    },
                    {
                        "risk_id": "RSK-002",
                        "requirement_id": "REQ-002",
                        "description": "HVAC threshold alerts delayed due to async notification processing bottlenecks.",
                        "severity": "High",
                        "likelihood": "Medium",
                        "mitigation": "Simulate network delay and measure alert generation latency SLA.",
                        "source": "ai_inference"
                    }
                ]
            }
            return response_schema.model_validate(data)

        elif response_schema is ChangeImpactInfo:
            data = {
                "has_changes": True,
                "changed_files": ["app/services/telemetry.py"],
                "changed_functions": ["parse_sensor_reading"],
                "impacted_requirements": ["REQ-001"],
                "regression_risk": "Medium",
                "message": "Modification inside parse_sensor_reading impacts telemetry ingestion (REQ-001). Code updates could fail ingestion logic.",
                "source": "source_code"
            }
            return response_schema.model_validate(data)

        elif response_schema is CoverageInfo:
            data = {
                "mapped_requirements": ["REQ-001", "REQ-002"],
                "uncovered_requirements": ["REQ-003"],
                "coverage_percentage": 66.7,
                "source": "ai_inference"
            }
            return response_schema.model_validate(data)

        elif response_schema is TestStrategyInfo:
            data = {
                "unit_tests": [
                    "Verify parse_sensor_reading parser rejects invalid hex keys.",
                    "Verify AlertTrigger evaluates boundary thresholds."
                ],
                "integration_tests": [
                    "Ensure telemetry collector routes alerts to notifier dispatch queue."
                ],
                "api_tests": [
                    "Check POST /telemetry accepts Pydantic requests.",
                    "Test GET /alerts filter options."
                ],
                "tools": ["pytest", "httpx"],
                "environments": ["staging"],
                "source": "ai_inference"
            }
            return response_schema.model_validate(data)

        elif response_schema is TestCasesWrapper:
            # Check prompt context via a simple heuristic: negative/boundary mock uses different IDs
            # Default mock returns core positive/happy_path cases
            data = {
                "test_cases": [
                    {
                        "test_case_id": "TC-001",
                        "title": "Accept valid temperature telemetry payload",
                        "test_type": "api",
                        "test_category": "happy_path",
                        "requirement_id": "REQ-001",
                        "risk_id": "RSK-001",
                        "design_component": "Telemetry Collector",
                        "code_target": "POST /telemetry",
                        "description": "Verify the ingestion API accepts a valid sensor reading and persists it.",
                        "preconditions": [
                            "Telemetry Collector service is running in staging",
                            "Valid sensor device is registered",
                        ],
                        "steps": [
                            "Send POST /telemetry with a valid temperature reading",
                            "Verify HTTP 201 response",
                            "Query telemetry store for the new record",
                        ],
                        "assertions": [
                            "Response status is 201",
                            "Response body contains sensor_id and timestamp",
                            "Record exists in telemetry table",
                        ],
                        "expected_result": "Valid telemetry reading is accepted and stored.",
                        "mocks_required": [],
                        "test_data_ids": ["TD-001"],
                        "priority": "High",
                        "source": "ai_inference",
                    },
                    {
                        "test_case_id": "TC-002",
                        "title": "Trigger alert when threshold exceeded",
                        "test_type": "integration",
                        "test_category": "positive",
                        "requirement_id": "REQ-002",
                        "risk_id": "RSK-002",
                        "design_component": "Alert Notification Engine",
                        "code_target": "AlertTrigger.evaluate_threshold",
                        "description": "Verify alert is generated when reading exceeds configured HVAC threshold.",
                        "preconditions": [
                            "Alert threshold configured for test room",
                            "Notification queue is available",
                        ],
                        "steps": [
                            "Submit telemetry reading above threshold",
                            "Wait for alert evaluation pipeline",
                            "Check alert dispatch queue",
                        ],
                        "assertions": [
                            "Alert record created with severity matching threshold breach",
                            "Notification event published to alert queue",
                        ],
                        "expected_result": "Threshold breach produces a timely alert event.",
                        "mocks_required": ["notification_dispatcher"],
                        "test_data_ids": ["TD-002"],
                        "priority": "High",
                        "source": "ai_inference",
                    },
                    {
                        "test_case_id": "TC-003",
                        "title": "Verify telemetry collector microservice isolation",
                        "test_type": "integration",
                        "test_category": "positive",
                        "requirement_id": "REQ-003",
                        "risk_id": None,
                        "design_component": "Telemetry Collector",
                        "code_target": "TelemetryCollectorService",
                        "description": "Verify telemetry collector operates as an independent microservice.",
                        "preconditions": ["Microservice deployment is active"],
                        "steps": [
                            "Stop dependent services except Telemetry Collector",
                            "Send valid telemetry payload",
                            "Verify ingestion succeeds independently",
                        ],
                        "assertions": [
                            "Telemetry Collector accepts payload without other services",
                            "Service health endpoint returns healthy",
                        ],
                        "expected_result": "Telemetry Collector functions independently as a microservice.",
                        "mocks_required": [],
                        "test_data_ids": ["TD-001"],
                        "priority": "Medium",
                        "source": "ai_inference",
                    },
                    {
                        "test_case_id": "TC-007",
                        "title": "Verify user login via web UI",
                        "test_type": "ui",
                        "test_category": "happy_path",
                        "requirement_id": "REQ-001",
                        "risk_id": None,
                        "design_component": "Web UI",
                        "code_target": "LoginPage",
                        "description": "Verify that a registered user can log in through the web UI and reach the dashboard.",
                        "preconditions": [
                            "Web application is deployed to staging",
                            "Test user 'testuser' exists with known credentials",
                        ],
                        "steps": [
                            "Open the login page",
                            "Enter username and password",
                            "Click the login button",
                            "Verify dashboard loads"
                        ],
                        "assertions": [
                            "Dashboard main container is present",
                            "Welcome message contains username"
                        ],
                        "expected_result": "User is authenticated and dashboard is displayed.",
                        "ui_actions": [
                            {"action": "open", "url": "https://example.local/login"},
                            {"action": "input", "selector": "#username", "selector_strategy": "css", "value": "testuser"},
                            {"action": "input", "selector": "#password", "selector_strategy": "css", "value": "s3cret"},
                            {"action": "click", "selector": "#login", "selector_strategy": "css"},
                            {"action": "wait", "selector": "#dashboard", "selector_strategy": "css", "condition": "visible", "timeout": 10}
                        ],
                        "mocks_required": [],
                        "test_data_ids": ["TD-001"],
                        "priority": "High",
                        "source": "ai_inference",
                    },
                ]
            }
            return response_schema.model_validate(data)

        elif response_schema is TestScenariosWrapper:
            data = {
                "test_scenarios": [
                    {
                        "scenario_id": "SCN-001",
                        "title": "Threshold breach alert flow",
                        "description": "End-to-end business flow from sensor reading to alert generation.",
                        "flow_steps": [
                            "Sensor publishes temperature reading",
                            "Telemetry Collector ingests reading",
                            "Threshold evaluation detects breach",
                            "Alert Notification Engine generates alert",
                        ],
                        "requirement_ids": ["REQ-001", "REQ-002"],
                        "related_test_case_ids": ["TC-001", "TC-002"],
                        "source": "ai_inference",
                    },
                    {
                        "scenario_id": "SCN-002",
                        "title": "Independent telemetry microservice operation",
                        "description": "Verify telemetry collector operates independently per architecture.",
                        "flow_steps": [
                            "Deploy Telemetry Collector microservice",
                            "Send telemetry payload",
                            "Verify independent ingestion",
                        ],
                        "requirement_ids": ["REQ-003"],
                        "related_test_case_ids": ["TC-003"],
                        "source": "ai_inference",
                    },
                ]
            }
            return response_schema.model_validate(data)

        elif response_schema is TestDataWrapper:
            data = {
                "generated_test_data": [
                    {
                        "data_id": "TD-001",
                        "category": "valid",
                        "description": "Normal room temperature reading within acceptable range for REQ-001.",
                        "linked_test_case_ids": ["TC-001", "TC-003"],
                        "fields": [
                            {
                                "name": "sensor_id",
                                "value": "sensor-room-101",
                                "description": "Registered HVAC room sensor",
                            },
                            {
                                "name": "temperature_c",
                                "value": 22.5,
                                "description": "Normal operating temperature",
                            },
                            {
                                "name": "timestamp",
                                "value": "2026-08-15T10:00:00Z",
                                "description": "Recent valid reading time",
                            },
                        ],
                        "source": "ai_inference",
                    },
                    {
                        "data_id": "TD-002",
                        "category": "boundary",
                        "description": "Reading exactly at configured alert threshold for REQ-002.",
                        "linked_test_case_ids": ["TC-002"],
                        "fields": [
                            {
                                "name": "sensor_id",
                                "value": "sensor-room-101",
                                "description": "Same sensor with threshold configured",
                            },
                            {
                                "name": "temperature_c",
                                "value": 30.0,
                                "description": "Exact threshold boundary value",
                            },
                            {
                                "name": "threshold_c",
                                "value": 30.0,
                                "description": "Configured alert threshold",
                            },
                        ],
                        "source": "ai_inference",
                    },
                    {
                        "data_id": "TD-003",
                        "category": "invalid",
                        "description": "Malformed sensor identifier for negative API validation test.",
                        "linked_test_case_ids": ["TC-004"],
                        "fields": [
                            {
                                "name": "sensor_id",
                                "value": "!!!invalid!!!",
                                "description": "Violates sensor_id format rules",
                            },
                            {
                                "name": "temperature_c",
                                "value": 22.5,
                                "description": "Otherwise valid reading payload",
                            },
                        ],
                        "source": "ai_inference",
                    },
                ]
            }
            return response_schema.model_validate(data)

        elif response_schema is NegativeBoundaryTestCasesWrapper:
            data = {
                "test_cases": [
                    {
                        "test_case_id": "TC-004",
                        "title": "Reject telemetry with invalid sensor_id format",
                        "test_type": "api",
                        "test_category": "negative",
                        "requirement_id": "REQ-001",
                        "risk_id": None,
                        "design_component": "Telemetry Collector",
                        "code_target": "POST /telemetry",
                        "description": "Verify API rejects malformed sensor identifiers per ingestion validation rules.",
                        "preconditions": ["Telemetry Collector service is running"],
                        "steps": [
                            "Send POST /telemetry with invalid sensor_id",
                            "Capture response",
                        ],
                        "assertions": [
                            "Response status is 422",
                            "Error message identifies invalid sensor_id",
                        ],
                        "expected_result": "Invalid sensor_id is rejected without persisting data.",
                        "mocks_required": [],
                        "test_data_ids": ["TD-003"],
                        "priority": "Medium",
                        "source": "ai_inference",
                    },
                    {
                        "test_case_id": "TC-005",
                        "title": "Handle telemetry at exact threshold boundary",
                        "test_type": "unit",
                        "test_category": "boundary",
                        "requirement_id": "REQ-002",
                        "risk_id": "RSK-002",
                        "design_component": "Alert Notification Engine",
                        "code_target": "AlertTrigger.evaluate_threshold",
                        "description": "Verify alert behavior when reading equals exact threshold boundary.",
                        "preconditions": ["Threshold configured at 30.0C"],
                        "steps": [
                            "Submit reading at exact threshold value",
                            "Observe alert evaluation result",
                        ],
                        "assertions": [
                            "Alert is triggered at exact boundary per configuration",
                        ],
                        "expected_result": "Boundary threshold value triggers alert as configured.",
                        "mocks_required": [],
                        "test_data_ids": ["TD-002"],
                        "priority": "High",
                        "source": "ai_inference",
                    },
                    {
                        "test_case_id": "TC-006",
                        "title": "Regression: parse_sensor_reading handles changed parsing logic",
                        "test_type": "regression",
                        "test_category": "positive",
                        "requirement_id": "REQ-001",
                        "risk_id": "RSK-001",
                        "design_component": "Telemetry Collector",
                        "code_target": "parse_sensor_reading",
                        "description": "Verify modified parse_sensor_reading still accepts previously valid payloads.",
                        "preconditions": [
                            "Change metadata indicates telemetry.py was modified",
                        ],
                        "steps": [
                            "Invoke parse_sensor_reading with baseline valid payload",
                            "Compare parsed output to expected structure",
                        ],
                        "assertions": [
                            "Parser returns normalized reading object",
                            "No regression in field mapping",
                        ],
                        "expected_result": "Changed parser maintains backward compatibility for valid inputs.",
                        "mocks_required": [],
                        "test_data_ids": ["TD-001"],
                        "priority": "High",
                        "source": "ai_inference",
                    },
                ]
            }
            return response_schema.model_validate(data)

        else:
            raise ValueError(f"No mock generator defined for schema: {schema_name}")

# Shared singleton instance used across all intelligence nodes
gemini_service = GeminiService()

