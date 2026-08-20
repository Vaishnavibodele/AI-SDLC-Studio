import os
import json
from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from pydantic import Field
from typing import Any, List, Optional, Union

load_dotenv()

def get_content_text(content: Any) -> str:
    """Safely extracts plain string from LLM response or content object/list."""
    if hasattr(content, "content"):
        content = content.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content)

class MockChatModel(BaseChatModel):
    """A mock chat model that mimics requirement elicitation and outputs valid JSON when requested."""
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        last_user_msg = ""
        system_prompt = ""
        
        for m in messages:
            m_type = getattr(m, "type", "")
            m_role = getattr(m, "role", "") if hasattr(m, "role") else ""
            m_content = getattr(m, "content", "")
            
            print(f"[MockModel Debug] Msg type: {m_type}, role: {m_role}, content length: {len(str(m_content))}")
            
            if m_type == "system" or m_role == "system":
                system_prompt = m_content
            elif m_type == "user" or m_type == "human" or m_role == "user":
                last_user_msg = m_content

        response_content = ""
        is_srs_compiler = "compile" in system_prompt.lower() and "srs" in system_prompt.lower()
        is_memory_updater = "update the structured requirement memory" in system_prompt.lower() or "state manager" in system_prompt.lower()
        
        print(f"[MockModel Debug] is_srs_compiler: {is_srs_compiler}, is_memory_updater: {is_memory_updater}")
        
        # Multi-Agent development prompts routing checks
        last_msg_lower = last_user_msg.lower()
        if "planningengine" in last_msg_lower or "projectplanner" in last_msg_lower:
            manifest_list = [
                {
                    "path": "app/main.py",
                    "module": "backend",
                    "owner_agent": "BackendAgent",
                    "purpose": "FastAPI entry point containing REST APIs",
                    "depends_on": "",
                    "priority": 1,
                    "language": "python",
                    "security_sensitive": True,
                    "estimated_tokens": 1200,
                    "requirement_id": "REQ-003",
                    "design_section_id": "api_endpoints"
                },
                {
                    "path": "app/database.py",
                    "module": "database",
                    "owner_agent": "DatabaseAgent",
                    "purpose": "Database initialization and engine setup",
                    "depends_on": "",
                    "priority": 2,
                    "language": "python",
                    "security_sensitive": False,
                    "estimated_tokens": 800,
                    "requirement_id": "REQ-001",
                    "design_section_id": "database_tables"
                },
                {
                    "path": "frontend/index.html",
                    "module": "frontend",
                    "owner_agent": "FrontendAgent",
                    "purpose": "React web app client file",
                    "depends_on": "",
                    "priority": 3,
                    "language": "html",
                    "security_sensitive": False,
                    "estimated_tokens": 500,
                    "requirement_id": "REQ-002",
                    "design_section_id": "ui_requirements"
                },
                {
                    "path": "README.md",
                    "module": "doc",
                    "owner_agent": "DocumentationAgent",
                    "purpose": "Setup instructions and compile steps",
                    "depends_on": "",
                    "priority": 4,
                    "language": "markdown",
                    "security_sensitive": False,
                    "estimated_tokens": 300,
                    "requirement_id": "REQ-004",
                    "design_section_id": "constraints"
                }
            ]
            response_content = json.dumps(manifest_list, indent=2)
            
        # Check messages for test override triggers
        all_text = (" ".join(str(m.content) for m in messages) + " " + system_prompt).lower()
        is_ownership_conflict = "ownership-conflict" in all_text
        is_api_mismatch = "api-mismatch" in all_text
        is_syntax_error = "syntax-error" in all_text
        is_input_validation_fail = "input-validation-fail" in all_text
        is_planning_fail = "planning-fail" in all_text
        is_agent_fail = "agent-fail" in all_text
        is_artifact_fail = "artifact-fail" in all_text

        print(f"[MockModel Debug] is_ownership_conflict: {is_ownership_conflict}, is_api_mismatch: {is_api_mismatch}, is_syntax_error: {is_syntax_error}, is_agent_fail: {is_agent_fail}, is_planning_fail: {is_planning_fail}, is_input_validation_fail: {is_input_validation_fail}, is_artifact_fail: {is_artifact_fail}")
        if "quality assurance ba" in all_text or "consistency" in all_text:
            response_content = json.dumps({"conflicts": [], "duplicates": []})
        elif "databaseagent" in last_msg_lower or "databasedeveloperagent" in system_prompt.lower():
            if is_agent_fail:
                raise Exception("Mock Database Developer Agent Failure Exception")
            if is_ownership_conflict:
                response_content = """[FILE: app/database.py]
# app/database.py
from sqlalchemy import create_engine
DATABASE_URL = "sqlite:///./sdlc_studio_test.db"
engine = create_engine(DATABASE_URL)

[FILE: app/main.py]
# Conflict file claim
print("Conflict!")
"""
            else:
                response_content = """# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base

DATABASE_URL = "sqlite:///./sdlc_studio_test.db"
engine = create_engine(DATABASE_URL)
Base = declarative_base()
"""
            
        elif "backendagent" in last_msg_lower or "backenddeveloperagent" in system_prompt.lower():
            if is_syntax_error:
                response_content = """# app/main.py
def read_root()
    invalid python syntax error!
"""
            else:
                response_content = """# app/main.py
from fastapi import FastAPI
app = FastAPI(title="E-Commerce API")

@app.get("/api")
def read_root():
    return {"status": "success", "message": "E-Commerce App Store API"}

@app.post("/api/checkout")
def checkout(payload: dict):
    return {"status": "success", "charge_id": "ch_12345"}
"""
            
        elif "frontendagent" in last_msg_lower or "frontenddeveloperagent" in system_prompt.lower():
            if is_api_mismatch:
                response_content = """<!-- frontend/index.html -->
<!DOCTYPE html>
<html>
<body>
    <script>
        // Method mismatch: GET instead of POST
        fetch("/api/checkout", { method: "GET" });
    </script>
</body>
</html>
"""
            else:
                response_content = """<!-- frontend/index.html -->
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>E-Commerce App Store Client</title>
</head>
<body>
    <div id="root">Welcome to E-Commerce App Store Client UI</div>
    <script>
        fetch("/api/checkout", { method: "POST" });
    </script>
</body>
</html>
"""
            
        elif "apiintegrationagent" in last_msg_lower or "apiintegrationagent" in system_prompt.lower():
            response_content = json.dumps({"mismatches": [], "status": "COMPLETED"})
            
        elif "documentationagent" in last_msg_lower or "documentationagent" in system_prompt.lower():
            response_content = """# README.md
# E-Commerce App Store Scaffold

## Installation
Run:
`pip install -r requirements.txt`

## Execution
Run:
`uvicorn app.main:app --reload`
"""

        # Scenario 1: State Manager / Memory update
        elif is_memory_updater:
            # We must output a valid RequirementMemory JSON
            functional = ["User authentication and profile management", "Dashboard displaying project status"]
            kw_suffix = ""
            for kw in ["ownership-conflict", "api-mismatch", "syntax-error", "input-validation-fail", "planning-fail", "agent-fail", "artifact-fail"]:
                if kw in all_text:
                    kw_suffix = f" [TEST-KEYWORD: {kw}]"
                    break
            if kw_suffix:
                functional.append(f"Traceability override check{kw_suffix}")

            if "delivery" in last_user_msg.lower() or "food" in last_user_msg.lower():
                summary = "A food delivery platform."
                functional = ["Browse menus from local restaurants", "Place orders and make payments", "Real-time delivery tracking"]
                if kw_suffix:
                    functional.append(f"Traceability override check{kw_suffix}")
            elif "ecommerce" in last_user_msg.lower() or "shop" in last_user_msg.lower() or "store" in last_user_msg.lower() or "bookstore" in last_user_msg.lower():
                summary = "An e-commerce online platform."
                functional = ["Product catalog search", "Shopping cart checkout", "Stripe payment integration"]
                if kw_suffix:
                    functional.append(f"Traceability override check{kw_suffix}")
            else:
                summary = f"A custom application for: {last_user_msg}" if last_user_msg else "Initial requirements gathering."

            memory_dict = {
                "project_summary": summary,
                "business_goals": "Optimize user flow and automate tasks.",
                "target_users": ["End User", "Administrator"],
                "functional_requirements": functional,
                "non_functional_requirements": ["Response time under 2s", "Secure HTTPS communication"],
                "constraints": ["Must support modern web browsers"],
                "assumptions": ["Users have internet access"],
                "acceptance_criteria": ["All core functional tests pass"],
                "open_questions": []
            }
            response_content = json.dumps(memory_dict, indent=2)

        # Scenario 2: SRS Emitter / Compiler
        elif is_srs_compiler:
            # Infer project type from system prompt context
            is_food = "delivery" in system_prompt.lower() or "food" in system_prompt.lower()
            if is_food:
                p_name = "Food Delivery Platform"
                p_summary = "A highly scalable food delivery solution connecting customers with local restaurants."
                biz_objectives = "Increase monthly deliveries by 45% and restaurant sign-ups by 20% in the first quarter."
                scope = "Real-time menu viewing, order placement, stripe payment, and driver tracking."
                func_reqs = [
                    "The system shall display restaurant menus based on customer geo-location.",
                    "The system shall support order payment checkout using credit cards or digital wallets.",
                    "The system shall provide real-time status tracking updates for driver deliveries."
                ]
            else:
                p_name = "E-Commerce App Store"
                if "input-validation-fail" in all_text:
                    p_name = "Input-Validation-Fail App"
                elif "planning-fail" in all_text:
                    p_name = "Planning-Fail App"
                elif "agent-fail" in all_text:
                    p_name = "Agent-Fail App"
                elif "artifact-fail" in all_text:
                    p_name = "Artifact-Fail App"
                p_summary = f"A digital shopping experience allowing users to browse items, manage carts, and purchase merchandise online."
                biz_objectives = "Provide a frictionless shopping experience resulting in a 25% checkout conversion rate increase."
                scope = "Includes product catalogs, shopping cart modifications, checkout integrations, and admin inventory tools."
                func_reqs = [
                    "The system shall allow users to browse and search product catalogs by title and category.",
                    "The system shall allow users to add items to a persistent shopping cart and modify item counts.",
                    "The system shall process checkout orders and integrate Stripe for secure transaction billing."
                ]
                if "input-validation-fail" in all_text:
                    func_reqs.append("Traceability override check [TEST-KEYWORD: input-validation-fail]")
                elif "planning-fail" in all_text:
                    func_reqs.append("Traceability override check [TEST-KEYWORD: planning-fail]")
                elif "agent-fail" in all_text:
                    func_reqs.append("Traceability override check [TEST-KEYWORD: agent-fail]")
                elif "artifact-fail" in all_text:
                    func_reqs.append("Traceability override check [TEST-KEYWORD: artifact-fail]")

            srs_dict = {
                "project_name": p_name,
                "document_information": "Classification: Internal Confidentially. Author: AI Business Analyst. Organization: SDLC Studio Labs.",
                "revision_history": "v1.0.0 (2026-07-26) - Initial draft compilation. v1.1.0 (2026-07-26) - Added security policies.",
                "approval_history": "Approved by Lead BA on 2026-07-26. Awaiting final product manager approval.",
                "executive_summary": f"This document defines requirements for the {p_name}. It forms the contract between business stakeholders and software engineers." + (" [TEST-KEYWORD: ownership-conflict]" if is_ownership_conflict else " [TEST-KEYWORD: api-mismatch]" if is_api_mismatch else " [TEST-KEYWORD: syntax-error]" if is_syntax_error else " [TEST-KEYWORD: input-validation-fail]" if is_input_validation_fail else " [TEST-KEYWORD: planning-fail]" if is_planning_fail else " [TEST-KEYWORD: agent-fail]" if is_agent_fail else " [TEST-KEYWORD: artifact-fail]" if is_artifact_fail else ""),
                "problem_statement": "Manual procedures and outdated offline systems slow down throughput, increase processing overhead, and degrade user satisfaction.",
                "business_objectives": biz_objectives,
                "stakeholders": ["Business Sponsors", "Platform Administrators", "Customer Service Representatives"],
                "user_personas": ["John - The convenience-focused customer", "Sarah - The store administrator"],
                "actors": ["Customer", "Admin API Client", "Stripe Payment Gateway", "Geolocation Map Engine"],
                "scope": scope,
                "out_of_scope": "Offline operations, custom logistics fleet management tools, and physical point-of-sale terminal support.",
                "business_requirements": [
                    "The system must secure transactions using industry-standard protocols.",
                    "The platform must comply with local consumer privacy laws (GDPR, PCI-DSS)."
                ],
                "functional_requirements": func_reqs,
                "non_functional_requirements": [
                    "The response time for catalogs search inquiries shall be under 2 seconds.",
                    "The system shall maintain 99.9% uptime availability during operational hours."
                ],
                "business_rules": [
                    "Orders exceeding $100 shall qualify for free standard shipping.",
                    "Accounts must be verified using email validation before making their first transaction."
                ],
                "user_stories": [
                    "As a Customer, I want to add products to my cart, so that I can buy them together.",
                    "As an Admin, I want to update product stock, so that customers see real-time inventory."
                ],
                "use_cases": [
                    "Use Case 1: Place Checkout Order. Trigger: User clicks checkout. Actor: Customer. Steps: Verify cart, input shipping, process payment, confirm."
                ],
                "acceptance_criteria": [
                    "Payment must receive a valid token from Stripe before saving order.",
                    "Cart items quantity cannot exceed active store inventory."
                ],
                "ui_requirements": [
                    "The interface shall use responsive grid styling compatible with mobile and desktop devices.",
                    "All click interactions shall provide clear focus outlines and micro-transition feedback."
                ],
                "navigation_flow": [
                    "Path: Landing Page -> Search Results -> Item Details -> Shopping Cart -> Checkout -> Confirmation Screen"
                ],
                "data_requirements": [
                    "The database shall store persistent audit logs for all financial operations.",
                    "User credentials must be encrypted using secure hashes prior to database writing."
                ],
                "security_requirements": [
                    "All communications must be encrypted using TLS 1.3.",
                    "API calls must be authorized using bearer JSON Web Tokens (JWT)."
                ],
                "integration_requirements": [
                    "Integrate Stripe Payment Gateway API.",
                    "Integrate SendGrid API for transactional notifications."
                ],
                "performance_requirements": [
                    "The API must handle up to 500 concurrent read requests without performance degradation."
                ],
                "compliance_requirements": [
                    "Payment processes must satisfy PCI-DSS level 1 guidelines."
                ],
                "constraints": [
                    "Backend must use Python FastAPI with SQLite relational database."
                ],
                "assumptions": [
                    "Customers have internet connectivity supporting TLS 1.2 or above."
                ],
                "risks": [
                    "Third-party Stripe API outages. Mitigation: Implement robust checkout exception queue."
                ],
                "dependencies": [
                    "FastAPI Framework, SQLAlchemy ORM, ReportLab PDF Writer, python-docx."
                ],
                "requirement_traceability_matrix": [
                    {"id": "REQ-001", "title": "Catalog Search", "description": "Browse and search product catalogs.", "category": "Functional"},
                    {"id": "REQ-002", "title": "Cart Management", "description": "Add items to shopping cart and change count.", "category": "Functional"},
                    {"id": "REQ-003", "title": "Stripe Checkout", "description": "Process payments using Stripe.", "category": "Functional"},
                    {"id": "REQ-004", "title": "Performance Latency", "description": "Search requests under 2 seconds.", "category": "Non-Functional"}
                ]
            }
            response_content = json.dumps(srs_dict, indent=2)

        # Scenario 2.5: SDD Emitter / Compiler
        elif "architect" in system_prompt.lower() or "sdd" in system_prompt.lower() or "software design document" in system_prompt.lower():
            # Infer project type from system prompt context
            is_food = "delivery" in system_prompt.lower() or "food" in system_prompt.lower()
            if is_food:
                p_name = "Food Delivery Platform"
                intro = "This document presents the detailed architectural design and specifications for the Food Delivery platform."
                tech_stack = ["FastAPI", "React", "PostgreSQL", "Redis for tracking cache", "Docker"]
                tables = [
                    {
                        "name": "users",
                        "columns": [
                            {"name": "id", "type": "VARCHAR(36)", "nullable": False, "description": "Primary key UUID"},
                            {"name": "email", "type": "VARCHAR(255)", "nullable": False, "description": "Unique email"},
                            {"name": "password_hash", "type": "VARCHAR(255)", "nullable": False, "description": "Hashed password"}
                        ],
                        "primary_key": "id",
                        "foreign_keys": [],
                        "constraints": ["UNIQUE(email)"]
                    },
                    {
                        "name": "orders",
                        "columns": [
                            {"name": "id", "type": "VARCHAR(36)", "nullable": False, "description": "Primary key UUID"},
                            {"name": "customer_id", "type": "VARCHAR(36)", "nullable": False, "description": "Foreign key to users"},
                            {"name": "restaurant_name", "type": "VARCHAR(255)", "nullable": False, "description": "Selected restaurant"},
                            {"name": "total_amount", "type": "DECIMAL(10,2)", "nullable": False, "description": "Total payment price"}
                        ],
                        "primary_key": "id",
                        "foreign_keys": [
                            {"column": "customer_id", "references_table": "users", "references_column": "id"}
                        ],
                        "constraints": []
                    }
                ]
                apis = [
                    {
                        "method": "POST",
                        "path": "/api/orders/place",
                        "request_body": "{ 'restaurant_id': 'string', 'items': [{'id': 'string', 'quantity': 1}] }",
                        "response_body": "{ 'order_id': 'string', 'status': 'PENDING' }",
                        "description": "Places a new food order."
                    }
                ]
                traceability = [
                    {
                        "requirement_id": "REQ-003",
                        "module": "Order Processor",
                        "api_endpoint": "POST /api/orders/place",
                        "db_table": "orders",
                        "ui_screen": "Checkout screen"
                    }
                ]
            else:
                p_name = "E-Commerce App Store"
                if "input-validation-fail" in all_text:
                    p_name = "Input-Validation-Fail App"
                elif "planning-fail" in all_text:
                    p_name = "Planning-Fail App"
                elif "agent-fail" in all_text:
                    p_name = "Agent-Fail App"
                elif "artifact-fail" in all_text:
                    p_name = "Artifact-Fail App"
                intro = f"This document presents the detailed architectural design and specifications for the {p_name}."
                tech_stack = ["FastAPI", "React", "PostgreSQL", "Docker", "Stripe API SDK"]
                tables = [
                    {
                        "name": "users",
                        "columns": [
                            {"name": "id", "type": "VARCHAR(36)", "nullable": False, "description": "Primary key UUID"},
                            {"name": "email", "type": "VARCHAR(255)", "nullable": False, "description": "Unique user email"},
                            {"name": "password_hash", "type": "VARCHAR(255)", "nullable": False, "description": "Hashed user credentials"}
                        ],
                        "primary_key": "id",
                        "foreign_keys": [],
                        "constraints": ["UNIQUE(email)"]
                    },
                    {
                        "name": "orders",
                        "columns": [
                            {"name": "id", "type": "VARCHAR(36)", "nullable": False, "description": "Primary key UUID"},
                            {"name": "user_id", "type": "VARCHAR(36)", "nullable": False, "description": "Foreign key to users"},
                            {"name": "total_amount", "type": "DECIMAL(10,2)", "nullable": False, "description": "Order total cost"}
                        ],
                        "primary_key": "id",
                        "foreign_keys": [
                            {"column": "user_id", "references_table": "users", "references_column": "id"}
                        ],
                        "constraints": []
                    }
                ]
                apis = [
                    {
                        "method": "POST",
                        "path": "/api/orders/checkout",
                        "request_body": "{ 'items': [{'id': 'string', 'quantity': 1}], 'stripe_token': 'string' }",
                        "response_body": "{ 'order_id': 'string', 'charge_status': 'success' }",
                        "description": "Submits checkout cart items and charges customer billing credit card."
                    }
                ]
                traceability = [
                    {
                        "requirement_id": "REQ-003",
                        "module": "Checkout Module",
                        "api_endpoint": "POST /api/orders/checkout",
                        "db_table": "orders",
                        "ui_screen": "Payment confirmation screen"
                    }
                ]

            sdd_dict = {
                "cover_page": f"SOFTWARE DESIGN DOCUMENT\nProject: {p_name}\nAuthor: Lead Architect\nOrganization: SDLC Studio Labs\nClassification: Internal Confidentially",
                "revision_history": "v1.0.0 (2026-07-26) - Initial architecture definition. v1.1.0 (2026-07-26) - Added security parameters.",
                "approval_history": "Reviewed by Lead Architect on 2026-07-26. Awaiting final PM signature.",
                "introduction": intro + (" [TEST-KEYWORD: ownership-conflict]" if is_ownership_conflict else " [TEST-KEYWORD: api-mismatch]" if is_api_mismatch else " [TEST-KEYWORD: syntax-error]" if is_syntax_error else ""),
                "design_goals": "Target SLA: 99.9% uptime. API latency < 2s. Support horizontal container scale.",
                "system_overview": "Three-tier architecture: React web app client, FastAPI REST gateway application server, PostgreSQL database store.",
                "high_level_architecture": "Clean Architecture implementation with segregated UI layers, API routing, business services, and database gateways.",
                "low_level_architecture": "Details submodules: authentication services, ordering checkouts, payment managers, and inventory sync processes.",
                "module_breakdown": "API Layer: main.py, routers/. Domain Layer: services/, models/. Repository Layer: database.py, repositories/.",
                
                # Mermaid Diagrams syntax fields
                "system_context_diagram_mermaid": f"graph TD\n  User[Customer] -->|Browse & Order| System[{p_name}]\n  System -->|Process Payment| PaymentGateway[Stripe API]",
                "use_case_diagram_mermaid": "left to right direction\nactor Customer\nactor Administrator\nrectangle System {\n  Customer --> (Browse Products)\n  Customer --> (Checkout Orders)\n  Administrator --> (Update Catalog)\n}",
                "component_diagram_mermaid": "graph TD\n  subgraph Client App\n    UI[React Web App]\n  end\n  subgraph Backend Gateway\n    Controller[FastAPI Router] --> Service[Order Service]\n  end\n  subgraph Database Layer\n    Service --> Repo[SQLAlchemy Repository]\n    Repo --> DB[(PostgreSQL Database)]\n  end\n  UI -->|HTTP POST| Controller",
                "class_diagram_mermaid": "classDiagram\n  class User {\n    +String id\n    +String email\n    +login()\n  }\n  class Order {\n    +String id\n    +Float totalAmount\n    +save()\n  }\n  User --> Order",
                "sequence_diagram_mermaid": "sequenceDiagram\n  actor Customer\n  Customer->>UI: Click Purchase\n  UI->>Gateway: POST /api/orders/checkout\n  Gateway->>Stripe: Charge Token\n  Stripe-->>Gateway: Charge Approved\n  Gateway->>Database: Save Order Record\n  Database-->>Gateway: Save Success\n  Gateway-->>UI: Confirm Order ID\n  UI-->>Customer: Display Success Screen",
                "activity_diagram_mermaid": "graph TD\n  Start([Start]) --> Browse[Browse Items] --> Cart[Add to Cart] --> Check[Checkout Payment] --> End([End])",
                "er_diagram_mermaid": "erDiagram\n  users ||--o{ orders : places\n  users {\n    string id PK\n    string email\n  }\n  orders {\n    string id PK\n    string user_id FK\n    float total_amount\n  }",
                "deployment_diagram_mermaid": "graph TD\n  subgraph AWS Cloud\n    ALB[Application Load Balancer] --> ECS[FastAPI Container Service]\n    ECS --> RDS[(Managed RDS Database)]\n  end",
                "flow_diagram_mermaid": "graph TD\n  Step1[Browse products] --> Step2[Modify quantities] --> Step3[Submit stripe payment]",
                "db_relationship_diagram_mermaid": "graph TD\n  users -->|one-to-many| orders",
                
                "database_design_overview": "Relational schema design implemented on PostgreSQL database. Strict foreign keys enforce integrity constraints.",
                "database_tables": tables,
                "database_relationships": ["users table contains a one-to-many relation with orders table linked via user_id column."],
                "database_constraints": ["FOREIGN KEY (user_id) REFERENCES users(id)", "UNIQUE(email) on users table."],
                
                "api_design_overview": "RESTful endpoints communicating in JSON payloads. Uses standard HTTP response templates (200, 201, 400, 404, 500).",
                "api_endpoints": apis,
                "authentication_flow": "Stateless authentication via secure JSON Web Tokens (JWT). Passwords hashed using bcrypt prior to database insertion.",
                "authorization_flow": "Role-Based Access Control (RBAC). Admin routes are gated with specific check decorator checks.",
                
                "security_design_policies": "All communications encrypted via TLS 1.3. CORS origins white-listed. SQL injection prevented using parameters binding.",
                "logging_strategy": "Structured JSON logging containing correlation IDs, log level parameters, and trace logs. Outputs to console stdout.",
                "exception_handling": "Global middleware intercepts exceptions, logs stack trace data, and returns formatted error payloads with stable codes.",
                "configuration_management": "System configuration parameters loaded dynamically from secure environment variables and Vault files.",
                
                "technology_stack": tech_stack,
                "folder_structure": "src/\n  main.py\n  api/\n    routers/\n  core/\n    config.py\n  services/\n  models/\n  repositories/\ntests/",
                "coding_standards": "Enforce PEP-8 guidelines. Static code checks verified using flake8 and black. PR reviews require approvals.",
                
                "performance_design": "Index primary keys and search fields. Implement connection pooling on DB engines. Cache configuration states.",
                "scalability_design": "FastAPI containers deployed as stateless cluster nodes under ALB. Scale thresholds defined at 75% average CPU limits.",
                "availability_design": "Multi-AZ database replica deployments with automatic health checking and failover systems. target SLA is 99.9% uptime.",
                
                "monitoring_strategy": "Expose Prometheus scraping endpoints. Alert notifications triggered when error rates exceed 1% within a 5-minute interval.",
                "backup_strategy": "Automated snapshot snapshots taken daily with a 30-day retention policy. Transaction logs replicated continuously.",
                "disaster_recovery_runbook": "Backup restoration recovery procedures run quarterly. RPO target is 24 hours. RTO target is 4 hours.",
                "architectural_risks": ["Potential stripe gateway response lag during peak periods. Mitigation: Queue client retry processes."],
                "design_assumptions": ["FastAPI container will scale horizontally under the AWS Application Load Balancer."],
                "future_enhancements": ["Integrate Redis query cache for catalogs.", "Develop custom recommendation model analytics."],
                "traceability_matrix": traceability
            }
            if is_input_validation_fail:
                if "database_tables" in sdd_dict:
                    del sdd_dict["database_tables"]
            response_content = json.dumps(sdd_dict, indent=2)

        # Scenario 2.7: Project Planner (Development Agent)
        elif "manifest" in system_prompt.lower() or "planner" in system_prompt.lower() or "manifest" in last_user_msg.lower():
            if is_planning_fail:
                raise Exception("Mock Planning Engine Failure Exception")
            manifest_list = [
                {
                    "path": "app/main.py",
                    "module": "backend",
                    "owner_agent": "CodeGenerator",
                    "purpose": "FastAPI entry point containing REST APIs",
                    "depends_on": "",
                    "priority": 1,
                    "language": "python",
                    "security_sensitive": True,
                    "estimated_tokens": 1200
                },
                {
                    "path": "app/database.py",
                    "module": "database",
                    "owner_agent": "CodeGenerator",
                    "purpose": "Database initialization and engine setup",
                    "depends_on": "",
                    "priority": 2,
                    "language": "python",
                    "security_sensitive": False,
                    "estimated_tokens": 800
                },
                {
                    "path": "frontend/index.html",
                    "module": "frontend",
                    "owner_agent": "CodeGenerator",
                    "purpose": "React web app client file",
                    "depends_on": "",
                    "priority": 3,
                    "language": "html",
                    "security_sensitive": False,
                    "estimated_tokens": 500
                },
                {
                    "path": "README.md",
                    "module": "doc",
                    "owner_agent": "CodeGenerator",
                    "purpose": "Setup instructions and compile steps",
                    "depends_on": "",
                    "priority": 4,
                    "language": "markdown",
                    "security_sensitive": False,
                    "estimated_tokens": 300
                }
            ]
            response_content = json.dumps(manifest_list, indent=2)

        # Scenario 2.8: Code Generator (Development Agent)
        elif "source code" in system_prompt.lower() or "file path:" in last_user_msg.lower() or "source code" in last_user_msg.lower() or "code content" in system_prompt.lower() or "agent" in system_prompt.lower() or "developer" in system_prompt.lower() or "database" in system_prompt.lower() or "backend" in system_prompt.lower() or "frontend" in system_prompt.lower():
            if is_agent_fail:
                raise Exception("Mock Agent Worker Failure Exception")
            last_msg_lower = last_user_msg.lower()
            if "main.py" in last_msg_lower or "main" in last_msg_lower:
                response_content = """# app/main.py
from fastapi import FastAPI
app = FastAPI(title="E-Commerce API")

@app.get("/api")
def read_root():
    return {"status": "success", "message": "E-Commerce App Store API"}

@app.post("/api/checkout")
def checkout(payload: dict):
    return {"status": "success", "charge_id": "ch_12345"}
"""
            elif "database.py" in last_msg_lower or "database" in last_msg_lower:
                response_content = """# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base

DATABASE_URL = "sqlite:///./sdlc_studio_test.db"
engine = create_engine(DATABASE_URL)
Base = declarative_base()
"""
            elif "index.html" in last_msg_lower or "index" in last_msg_lower:
                response_content = """<!-- frontend/index.html -->
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>E-Commerce App Store Client</title>
</head>
<body>
    <div id="root">Welcome to E-Commerce App Store Client UI</div>
</body>
</html>
"""
            else:
                response_content = """# README.md
# E-Commerce App Store Scaffold

## Installation
Run:
`pip install -r requirements.txt`

## Execution
Run:
`uvicorn app.main:app --reload`
"""

        # Scenario 3: Conversational Chat
        else:
            if not last_user_msg:
                response_content = "Hello! I am your AI Business Analyst. What kind of application are we building today?"
            elif "generate" in last_user_msg.lower() or "srs" in last_user_msg.lower() or "finish" in last_user_msg.lower():
                response_content = "I have collected sufficient information. Let's compile and generate the SRS document now!"
            else:
                response_content = f"Got it. I have noted that down. Can you tell me more about the primary target users and if there are any specific tech constraints we need to know about?"

        ai_message = AIMessage(content=response_content)
        return ChatResult(generations=[ChatGeneration(message=ai_message)])

    @property
    def _llm_type(self) -> str:
        return "mock-sdlc-model"


def get_llm() -> BaseChatModel:
    # Force MockChatModel only if MOCK_MODE is true
    if os.getenv("MOCK_MODE", "false").lower() == "true":
        print("[LLM Provider] MOCK_MODE is true. Forcing MockChatModel.")
        return MockChatModel()
        
    provider = os.getenv("DEFAULT_LLM_PROVIDER", "gemini").lower()
    model_name = os.getenv("DEFAULT_LLM_MODEL", "")

    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    has_gemini = bool(os.getenv("GEMINI_API_KEY"))
    has_anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))

    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key and not os.getenv("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = gemini_key

    if provider == "openai" and has_openai:
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=model_name or "gpt-4o", temperature=0.2)
        except ImportError as ie:
            print(f"[LLM Provider] langchain_openai import error: {ie}")
    elif provider == "gemini" and has_gemini:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(model=model_name or "gemini-3.6-flash", api_key=gemini_key, temperature=0.2)
        except Exception as ie:
            print(f"[LLM Provider] langchain_google_genai error: {ie}")
    elif provider == "anthropic" and has_anthropic:
        try:
            from langchain_community.chat_models import ChatAnthropic
            return ChatAnthropic(model=model_name or "claude-3-5-sonnet", temperature=0.2)
        except ImportError as ie:
            print(f"[LLM Provider] langchain_community import error: {ie}")

    # Fallback to active key if default provider isn't configured
    if has_gemini:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(model="gemini-3.6-flash", api_key=gemini_key, temperature=0.2)
        except Exception:
            pass
    if has_openai:
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
        except Exception:
            pass

    # If no keys or dependencies missing, fallback to MockChatModel to prevent server crash
    print("[LLM Provider] No active LLM provider configured or available. Falling back to MockChatModel.")
    return MockChatModel()
