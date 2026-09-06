/**
 * AI-SDLC Testing Agent - 8-Phase Frontend Controller
 * Complete integration with FastAPI Testing Agent backend.
 */

// ===========================================================================
// 1. SPECIFICATION PRESETS
// ===========================================================================

const PRESETS = {
    "smart-building": {
        project_id: "smart-building-001",
        srs: {
            title: "Smart Building Telemetry & Ingestion SRS",
            version: "1.0.0",
            features: [
                "Real-time temperature and humidity telemetry collection from distributed IoT sensor nodes",
                "HVAC automated threshold evaluation and immediate anomalous alert dispatch",
                "Isolated microservice telemetry ingestion architecture with strict zero-loss buffer guarantees"
            ]
        },
        sdd: {
            architecture: "Event-driven microservices architecture",
            components: [
                "Telemetry Ingestion Collector",
                "Alert Notification Engine",
                "Sensor Data Normalizer",
                "TimescaleDB State Store"
            ],
            interfaces: [
                "Ingestion REST API (/api/v1/telemetry)",
                "Alert Event Webhook Stream",
                "Sensor Health Diagnostic RPC"
            ]
        },
        source_code: {
            repository: "github.com/org/smart-building-telemetry",
            language: "Python",
            files: [
                "app/main.py",
                "app/services/telemetry.py",
                "app/services/alerts.py",
                "app/models/sensor.py"
            ],
            changes: {
                changed_files: [
                    "app/services/telemetry.py",
                    "app/services/alerts.py"
                ],
                changed_functions: [
                    "parse_sensor_reading",
                    "evaluate_temperature_threshold"
                ]
            }
        },
        api_docs: {
            base_url: "https://api.smartbuilding.internal",
            endpoints: [
                "POST /api/v1/telemetry",
                "GET /api/v1/alerts",
                "GET /health"
            ]
        },
        database_schema: {
            dialect: "PostgreSQL",
            tables: [
                "telemetry_readings",
                "alert_events",
                "sensor_nodes"
            ]
        },
        test_data: {
            fixtures: [
                "nominal_temperature_payload",
                "high_heat_threshold_payload",
                "malformed_sensor_uuid_payload"
            ]
        },
        environment: {
            name: "staging-cluster-eu-west-1"
        }
    },
    "auth-service": {
        project_id: "auth-service-002",
        srs: {
            title: "Identity & Access Management (IAM) SRS",
            version: "2.1.0",
            features: [
                "OAuth2 Password grant and JWT token issuance with RSA256 signature",
                "Time-based One-Time Password (TOTP) Multi-Factor Authentication",
                "Automated token blacklist revocation on user session logout"
            ]
        },
        sdd: {
            architecture: "Hexagonal Layered Architecture",
            components: [
                "Authentication Controller",
                "JWT Token Manager",
                "User Credentials Repository",
                "MFA Validator Service"
            ],
            interfaces: [
                "POST /oauth/token",
                "POST /mfa/verify",
                "POST /auth/logout"
            ]
        },
        source_code: {
            repository: "github.com/org/iam-auth-service",
            language: "Go",
            files: [
                "main.go",
                "token.go",
                "user.go",
                "mfa.go"
            ],
            changes: {
                changed_files: [
                    "token.go"
                ],
                changed_functions: [
                    "GenerateJwtToken",
                    "RevokeUserSession"
                ]
            }
        },
        api_docs: {
            base_url: "https://iam.internal.auth",
            endpoints: [
                "POST /oauth/token",
                "POST /mfa/verify",
                "POST /auth/logout"
            ]
        },
        database_schema: {
            dialect: "PostgreSQL",
            tables: [
                "accounts",
                "revoked_tokens",
                "mfa_secrets"
            ]
        },
        test_data: {
            fixtures: [
                "valid_admin_credentials",
                "expired_jwt_token",
                "invalid_totp_code"
            ]
        },
        environment: {
            name: "sandbox-qa"
        }
    },
    "empty": {
        project_id: "custom-project-001",
        srs: { title: "", version: "1.0.0", features: [] },
        sdd: { architecture: "", components: [], interfaces: [] },
        source_code: { repository: "", language: "Python", files: [], changes: { changed_files: [], changed_functions: [] } },
        api_docs: { base_url: "", endpoints: [] },
        database_schema: { dialect: "PostgreSQL", tables: [] },
        test_data: { fixtures: [] },
        environment: { name: "local" }
    }
};

// ===========================================================================
// 2. CENTRALIZED API SERVICE LAYER
// ===========================================================================

const ApiService = {
    candidateUrls: [
        'http://127.0.0.1:8085',
        'http://localhost:8085',
        'http://127.0.0.1:8000',
        'http://localhost:8000',
        '/api'
    ],
    activeBaseUrl: 'http://127.0.0.1:8085',
    isOnline: false,

    async detectBackendUrl() {
        for (const url of this.candidateUrls) {
            try {
                const res = await fetch(`${url}/`, { method: 'GET', headers: { 'Accept': 'application/json' } });
                if (res.ok) {
                    this.activeBaseUrl = url;
                    this.isOnline = true;
                    return url;
                }
            } catch (e) {
                // Try next
            }
        }
        this.isOnline = false;
        return this.activeBaseUrl;
    },

    async checkHealth() {
        try {
            const res = await fetch(`${this.activeBaseUrl}/`, { method: 'GET' });
            this.isOnline = res.ok;
            return this.isOnline;
        } catch (e) {
            const detected = await this.detectBackendUrl();
            return this.isOnline;
        }
    },

    async startTesting(payload) {
        const res = await fetch(`${this.activeBaseUrl}/testing/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail ? (typeof err.detail === 'object' ? JSON.stringify(err.detail) : err.detail) : `HTTP ${res.status}`);
        }
        return res.json();
    },

    async executeTesting(payload) {
        const res = await fetch(`${this.activeBaseUrl}/testing/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail ? (typeof err.detail === 'object' ? JSON.stringify(err.detail) : err.detail) : `HTTP ${res.status}`);
        }
        return res.json();
    },

    async getApprovalStatus(projectId) {
        const res = await fetch(`${this.activeBaseUrl}/testing/report/approval-status/${projectId}`, {
            method: 'GET'
        });
        if (!res.ok) return null;
        return res.json();
    },

    async approveReport(payload) {
        const res = await fetch(`${this.activeBaseUrl}/testing/report/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Approval failed');
        }
        return res.json();
    },

    async rejectReport(payload) {
        const res = await fetch(`${this.activeBaseUrl}/testing/report/reject`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Rejection failed');
        }
        return res.json();
    },

    async exportReportBlob(payload, format) {
        if (format === 'json') {
            return null; // Handle client-side JSON export
        }
        const res = await fetch(`${this.activeBaseUrl}/testing/report/export?fmt=${format}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            throw new Error(`Export ${format.toUpperCase()} failed`);
        }
        return res.blob();
    }
};

// ===========================================================================
// 3. APPLICATION STATE STORE
// ===========================================================================

const AppState = {
    activeEditorTab: 'visual',
    currentProjectId: 'smart-building-001',
    activePhaseTab: 'panel-phase1',
    
    // Cached response data across all 8 phases
    phase1Data: null,
    phase2Data: null,
    phase3Data: null,
    phase4Data: null,
    phase5Data: null,
    phase6Data: null,
    phase7Data: null,
    phase8Data: null,
    
    // Approval state
    approvalState: null,
    currentReport: null,
    
    // Filters
    cachedTestCases: [],
    selectedTestType: 'all',
    selectedPriority: 'all',
    selectedCategory: 'all'
};

// ===========================================================================
// 4. DOM ELEMENT REFERENCES
// ===========================================================================

let DOM = {};

function initDomReferences() {
    DOM = {
        serverStatus: document.getElementById('server-status'),
        btnRunAll: document.getElementById('btn-run-all'),
        btnRunIntelligence: document.getElementById('btn-run-intelligence'),
        presetSelect: document.getElementById('preset-select'),
        projectIdDisplay: document.getElementById('project-id-display'),
        
        tabVisual: document.getElementById('tab-visual'),
        tabJson: document.getElementById('tab-json'),
        visualForm: document.getElementById('visual-form'),
        jsonEditorContainer: document.getElementById('json-editor-container'),
        jsonTextarea: document.getElementById('json-textarea'),
        jsonSyntaxError: document.getElementById('json-syntax-error'),
        jsonErrorText: document.getElementById('json-error-text'),
        
        // Dynamic row containers
        srsFeaturesContainer: document.getElementById('srs-features-container'),
        sddComponentsContainer: document.getElementById('sdd-components-container'),
        codeFilesContainer: document.getElementById('code-files-container'),
        changedFilesContainer: document.getElementById('changed-files-container'),
        changedFunctionsContainer: document.getElementById('changed-functions-container'),
        apiEndpointsContainer: document.getElementById('api-endpoints-container'),
        dbTablesContainer: document.getElementById('db-tables-container'),
        
        // Optional cards
        toggleApi: document.getElementById('toggle-api'),
        toggleDb: document.getElementById('toggle-db'),
        toggleEnv: document.getElementById('toggle-env'),
        apiCard: document.getElementById('api-card'),
        dbCard: document.getElementById('db-card'),
        envCard: document.getElementById('env-card'),
        
        // Top Ribbon
        activeStageIndicator: document.getElementById('active-stage-indicator'),
        activeStageDesc: document.getElementById('active-stage-desc'),
        headerQualityScore: document.getElementById('header-quality-score'),
        headerQualityDesc: document.getElementById('header-quality-desc'),
        headerReadinessBadge: document.getElementById('header-readiness-badge'),
        headerReleaseAllowed: document.getElementById('header-release-allowed'),
        headerApprovalStatus: document.getElementById('header-approval-status'),
        headerApprovalReviewer: document.getElementById('header-approval-reviewer'),
        runStatusBadge: document.getElementById('run-status-badge'),
        
        // Loading & Empty states
        resultsEmptyState: document.getElementById('results-empty-state'),
        resultsLoadingState: document.getElementById('results-loading-state'),
        loadingTitle: document.getElementById('loading-title'),
        loadingNodeStatus: document.getElementById('loading-node-status'),
        loadingProgressFill: document.getElementById('loading-progress-fill'),
        resultsContent: document.getElementById('results-content'),
        validationErrorsAlert: document.getElementById('validation-errors-alert'),
        validationErrorsList: document.getElementById('validation-errors-list'),
        
        // Navigation buttons
        phaseNavBtns: document.querySelectorAll('.phase-nav-btn'),
        sidebarSubitems: document.querySelectorAll('.nav-subitem[data-phase-target]'),
        pipelineNodes: document.querySelectorAll('.pipeline-node'),
        
        // Modals
        modalReviewer: document.getElementById('modal-reviewer'),
        reviewerIdInput: document.getElementById('reviewer-id-input'),
        reviewerNotesInput: document.getElementById('reviewer-notes-input'),
        btnSubmitApproval: document.getElementById('btn-submit-approval'),
        btnCancelApproval: document.getElementById('btn-cancel-approval'),
        btnCloseReviewerModal: document.getElementById('btn-close-reviewer-modal'),
        
        modalScreenshot: document.getElementById('modal-screenshot'),
        modalScreenshotImg: document.getElementById('modal-screenshot-img'),
        modalScreenshotTitle: document.getElementById('modal-screenshot-title'),
        btnCloseScreenshotModal: document.getElementById('btn-close-screenshot-modal')
    };
}

// ===========================================================================
// 5. LIFECYCLE & INITIALIZATION
// ===========================================================================

document.addEventListener('DOMContentLoaded', async () => {
    initDomReferences();
    if (window.lucide) lucide.createIcons();

    // Check backend connectivity
    await updateBackendStatus();
    setInterval(updateBackendStatus, 4000);

    // Wire Presets & Form Sync
    DOM.presetSelect.addEventListener('change', (e) => loadPreset(e.target.value));
    DOM.tabVisual.addEventListener('click', () => setEditorMode('visual'));
    DOM.tabJson.addEventListener('click', () => setEditorMode('json'));

    // Wire Optional Checkboxes
    DOM.toggleApi.addEventListener('change', () => DOM.apiCard.classList.toggle('hidden', !DOM.toggleApi.checked));
    DOM.toggleDb.addEventListener('change', () => DOM.dbCard.classList.toggle('hidden', !DOM.toggleDb.checked));
    DOM.toggleEnv.addEventListener('change', () => DOM.envCard.classList.toggle('hidden', !DOM.toggleEnv.checked));

    // Wire Dynamic Row Adders
    document.getElementById('btn-add-srs-feature').addEventListener('click', () => addDynamicRow(DOM.srsFeaturesContainer, '', 'e.g. Real-time telemetry ingestion'));
    document.getElementById('btn-add-sdd-component').addEventListener('click', () => addDynamicRow(DOM.sddComponentsContainer, '', 'e.g. Telemetry Ingestion Collector'));
    document.getElementById('btn-add-code-file').addEventListener('click', () => addDynamicRow(DOM.codeFilesContainer, '', 'e.g. app/services/telemetry.py'));
    document.getElementById('btn-add-changed-file').addEventListener('click', () => addDynamicRow(DOM.changedFilesContainer, '', 'e.g. app/services/telemetry.py'));
    document.getElementById('btn-add-changed-function').addEventListener('click', () => addDynamicRow(DOM.changedFunctionsContainer, '', 'e.g. parse_sensor_reading'));
    document.getElementById('btn-add-api-endpoint').addEventListener('click', () => addDynamicRow(DOM.apiEndpointsContainer, '', 'e.g. POST /api/v1/telemetry'));
    document.getElementById('btn-add-db-table').addEventListener('click', () => addDynamicRow(DOM.dbTablesContainer, '', 'e.g. telemetry_readings'));

    // Wire 8-Phase Tab Navigation
    wirePhaseNavigation();

    // Wire Sub-tabs (in P2, P3, P6)
    wireSubTabs();

    // Wire Test Filters in Phase 3
    wirePhase3Filters();

    // Wire Execution Triggers
    DOM.btnRunAll.addEventListener('click', () => executeWorkflow(true));
    DOM.btnRunIntelligence.addEventListener('click', () => executeWorkflow(false));

    // Wire Human Approval Actions
    wireApprovalActions();

    // Wire Report Exports
    wireReportExports();

    // Wire Modals
    wireModals();

    // Load default preset
    loadPreset('smart-building');
});

// ===========================================================================
// 6. BACKEND HEALTH POLLER
// ===========================================================================

async function updateBackendStatus() {
    const isOnline = await ApiService.checkHealth();
    if (isOnline) {
        DOM.serverStatus.className = 'status-indicator online';
        DOM.serverStatus.innerHTML = `<span class="status-dot"></span><span class="status-label">Backend Online (${ApiService.activeBaseUrl.replace('http://', '')})</span>`;
    } else {
        DOM.serverStatus.className = 'status-indicator offline';
        DOM.serverStatus.innerHTML = `<span class="status-dot"></span><span class="status-label">Backend Offline (Port 8085)</span>`;
    }
}

// ===========================================================================
// 7. PRESETS & FORM COMPILATION
// ===========================================================================

function loadPreset(key) {
    const template = PRESETS[key];
    if (!template) return;

    DOM.visualForm.reset();
    document.getElementById('project-id').value = template.project_id || '';
    document.getElementById('srs-title').value = template.srs.title || '';
    document.getElementById('srs-version').value = template.srs.version || '';
    document.getElementById('sdd-architecture').value = template.sdd.architecture || '';
    document.getElementById('code-repository').value = template.source_code.repository || '';
    document.getElementById('code-language').value = template.source_code.language || '';

    // Clear dynamic lists
    DOM.srsFeaturesContainer.innerHTML = '';
    DOM.sddComponentsContainer.innerHTML = '';
    DOM.codeFilesContainer.innerHTML = '';
    DOM.changedFilesContainer.innerHTML = '';
    DOM.changedFunctionsContainer.innerHTML = '';
    DOM.apiEndpointsContainer.innerHTML = '';
    DOM.dbTablesContainer.innerHTML = '';

    (template.srs.features || []).forEach(f => addDynamicRow(DOM.srsFeaturesContainer, f, 'Requirement details'));
    (template.sdd.components || []).forEach(c => addDynamicRow(DOM.sddComponentsContainer, c, 'Component name'));
    (template.source_code.files || []).forEach(f => addDynamicRow(DOM.codeFilesContainer, f, 'File path'));

    if (template.source_code.changes) {
        (template.source_code.changes.changed_files || []).forEach(f => addDynamicRow(DOM.changedFilesContainer, f, 'Changed file'));
        (template.source_code.changes.changed_functions || []).forEach(fn => addDynamicRow(DOM.changedFunctionsContainer, fn, 'Changed function'));
    }

    if (template.api_docs && template.api_docs.base_url) {
        DOM.toggleApi.checked = true;
        DOM.apiCard.classList.remove('hidden');
        document.getElementById('api-base-url').value = template.api_docs.base_url;
        (template.api_docs.endpoints || []).forEach(ep => addDynamicRow(DOM.apiEndpointsContainer, ep, 'Endpoint'));
    } else {
        DOM.toggleApi.checked = false;
        DOM.apiCard.classList.add('hidden');
    }

    if (template.database_schema && template.database_schema.dialect) {
        DOM.toggleDb.checked = true;
        DOM.dbCard.classList.remove('hidden');
        document.getElementById('db-dialect').value = template.database_schema.dialect;
        (template.database_schema.tables || []).forEach(t => addDynamicRow(DOM.dbTablesContainer, t, 'Table name'));
    } else {
        DOM.toggleDb.checked = false;
        DOM.dbCard.classList.add('hidden');
    }

    if (template.environment && template.environment.name) {
        DOM.toggleEnv.checked = true;
        DOM.envCard.classList.remove('hidden');
        document.getElementById('env-name').value = template.environment.name;
    } else {
        DOM.toggleEnv.checked = false;
        DOM.envCard.classList.add('hidden');
    }

    DOM.jsonTextarea.value = JSON.stringify(template, null, 2);
    AppState.currentProjectId = template.project_id || 'smart-building-001';
    DOM.projectIdDisplay.textContent = `PROJECT: ${AppState.currentProjectId}`;
}

function compilePayload() {
    if (AppState.activeEditorTab === 'json') {
        try {
            const data = JSON.parse(DOM.jsonTextarea.value);
            DOM.jsonSyntaxError.classList.add('hidden');
            return data;
        } catch (e) {
            DOM.jsonSyntaxError.classList.remove('hidden');
            DOM.jsonErrorText.textContent = `JSON Error: ${e.message}`;
            throw e;
        }
    }

    const srsFeatures = Array.from(DOM.srsFeaturesContainer.querySelectorAll('input')).map(i => i.value.trim()).filter(Boolean);
    const sddComponents = Array.from(DOM.sddComponentsContainer.querySelectorAll('input')).map(i => i.value.trim()).filter(Boolean);
    const codeFiles = Array.from(DOM.codeFilesContainer.querySelectorAll('input')).map(i => i.value.trim()).filter(Boolean);
    const changedFiles = Array.from(DOM.changedFilesContainer.querySelectorAll('input')).map(i => i.value.trim()).filter(Boolean);
    const changedFunctions = Array.from(DOM.changedFunctionsContainer.querySelectorAll('input')).map(i => i.value.trim()).filter(Boolean);

    const payload = {
        project_id: document.getElementById('project-id').value.trim() || 'smart-building-001',
        srs: {
            title: document.getElementById('srs-title').value.trim(),
            version: document.getElementById('srs-version').value.trim(),
            features: srsFeatures
        },
        sdd: {
            architecture: document.getElementById('sdd-architecture').value.trim(),
            components: sddComponents
        },
        source_code: {
            repository: document.getElementById('code-repository').value.trim(),
            language: document.getElementById('code-language').value.trim(),
            files: codeFiles,
            changes: {
                changed_files: changedFiles,
                changed_functions: changedFunctions
            }
        }
    };

    if (DOM.toggleApi.checked) {
        const eps = Array.from(DOM.apiEndpointsContainer.querySelectorAll('input')).map(i => i.value.trim()).filter(Boolean);
        payload.api_docs = {
            base_url: document.getElementById('api-base-url').value.trim(),
            endpoints: eps
        };
    }

    if (DOM.toggleDb.checked) {
        const tbls = Array.from(DOM.dbTablesContainer.querySelectorAll('input')).map(i => i.value.trim()).filter(Boolean);
        payload.database_schema = {
            dialect: document.getElementById('db-dialect').value.trim(),
            tables: tbls
        };
    }

    if (DOM.toggleEnv.checked) {
        payload.environment = {
            name: document.getElementById('env-name').value.trim()
        };
    }

    AppState.currentProjectId = payload.project_id;
    DOM.projectIdDisplay.textContent = `PROJECT: ${AppState.currentProjectId}`;
    return payload;
}

function setEditorMode(mode) {
    AppState.activeEditorTab = mode;
    if (mode === 'json') {
        const payload = compilePayload();
        DOM.jsonTextarea.value = JSON.stringify(payload, null, 2);
        DOM.tabVisual.classList.remove('active');
        DOM.tabJson.classList.add('active');
        DOM.visualForm.classList.add('hidden');
        DOM.jsonEditorContainer.classList.remove('hidden');
    } else {
        try {
            const data = JSON.parse(DOM.jsonTextarea.value);
            DOM.jsonSyntaxError.classList.add('hidden');
            // Sync back to visual
            document.getElementById('project-id').value = data.project_id || '';
            if (data.srs) {
                document.getElementById('srs-title').value = data.srs.title || '';
                document.getElementById('srs-version').value = data.srs.version || '';
            }
            DOM.tabJson.classList.remove('active');
            DOM.tabVisual.classList.add('active');
            DOM.jsonEditorContainer.classList.add('hidden');
            DOM.visualForm.classList.remove('hidden');
        } catch (e) {
            DOM.jsonSyntaxError.classList.remove('hidden');
            DOM.jsonErrorText.textContent = `Invalid JSON: ${e.message}. Fix before switching.`;
        }
    }
}

function addDynamicRow(container, value = '', placeholder = '') {
    const row = document.createElement('div');
    row.className = 'dynamic-item';
    const input = document.createElement('input');
    input.type = 'text';
    input.value = value;
    input.placeholder = placeholder;

    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'btn btn-danger btn-sm';
    del.innerHTML = '<i data-lucide="x"></i>';
    del.style.padding = '6px 10px';
    del.onclick = () => row.remove();

    row.appendChild(input);
    row.appendChild(del);
    container.appendChild(row);
    if (window.lucide) lucide.createIcons();
}

// ===========================================================================
// 8. NAVIGATION & WORKFLOW BAR WIRING
// ===========================================================================

function wirePhaseNavigation() {
    // Top Phase Tabs
    DOM.phaseNavBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            activatePhaseTab(btn.dataset.target);
        });
    });

    // Sidebar Subitems
    DOM.sidebarSubitems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            activatePhaseTab(item.dataset.phaseTarget);
        });
    });

    // Pipeline Nodes
    DOM.pipelineNodes.forEach(node => {
        node.addEventListener('click', () => {
            if (node.dataset.target) {
                activatePhaseTab(node.dataset.target);
            }
        });
    });
}

function activatePhaseTab(targetId) {
    if (!targetId) return;
    AppState.activePhaseTab = targetId;

    // Phase tabs
    DOM.phaseNavBtns.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.target === targetId);
    });

    // Sidebar
    DOM.sidebarSubitems.forEach(item => {
        item.classList.toggle('active', item.dataset.phaseTarget === targetId);
    });

    // Panels
    document.querySelectorAll('.phase-tab-panel').forEach(panel => {
        panel.classList.toggle('active', panel.id === targetId);
    });

    if (window.lucide) lucide.createIcons();
}

function wireSubTabs() {
    document.querySelectorAll('.sub-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const parentPanel = btn.closest('.phase-tab-panel');
            const targetSub = btn.dataset.subtarget;
            
            parentPanel.querySelectorAll('.sub-tab-btn').forEach(b => b.classList.remove('active'));
            parentPanel.querySelectorAll('.sub-panel').forEach(p => p.classList.remove('active'));
            
            btn.classList.add('active');
            const targetEl = document.getElementById(targetSub);
            if (targetEl) targetEl.classList.add('active');

            if (window.lucide) lucide.createIcons();
        });
    });
}

function wirePhase3Filters() {
    const typeSelect = document.getElementById('filter-test-type');
    const prioSelect = document.getElementById('filter-priority');
    const catSelect = document.getElementById('filter-category');

    if (typeSelect) typeSelect.addEventListener('change', (e) => {
        AppState.selectedTestType = e.target.value;
        applyPhase3Filters();
    });
    if (prioSelect) prioSelect.addEventListener('change', (e) => {
        AppState.selectedPriority = e.target.value;
        applyPhase3Filters();
    });
    if (catSelect) catSelect.addEventListener('change', (e) => {
        AppState.selectedCategory = e.target.value;
        applyPhase3Filters();
    });
}

// ===========================================================================
// 9. WORKFLOW EXECUTION ENGINE (PHASE 1-8)
// ===========================================================================

function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function resetPipelineNodes() {
    for (let i = 1; i <= 8; i++) {
        const node = document.getElementById(`node-p${i}`);
        if (node) node.className = 'pipeline-node';
        const arrow = document.getElementById(`arrow-${i}`);
        if (arrow) arrow.className = 'pipeline-arrow';
    }
}

async function animatePipelineStep(phaseNum, status = 'running', label = '') {
    const node = document.getElementById(`node-p${phaseNum}`);
    const arrow = document.getElementById(`arrow-${phaseNum - 1}`);

    if (arrow && phaseNum > 1) {
        arrow.className = 'pipeline-arrow completed';
    }

    if (node) {
        node.className = `pipeline-node ${status}`;
    }

    if (DOM.loadingNodeStatus) {
        DOM.loadingNodeStatus.textContent = label || `Executing Phase ${phaseNum}...`;
    }
    if (DOM.loadingProgressFill) {
        DOM.loadingProgressFill.style.width = `${(phaseNum / 8) * 100}%`;
    }
}

async function executeWorkflow(isFullExecution = true) {
    let payload;
    try {
        payload = compilePayload();
    } catch (e) {
        alert(`Validation Error: ${e.message}`);
        return;
    }

    // UI state transitions
    DOM.resultsEmptyState.classList.add('hidden');
    DOM.resultsContent.classList.add('hidden');
    DOM.validationErrorsAlert.classList.add('hidden');
    DOM.resultsLoadingState.classList.remove('hidden');

    DOM.btnRunAll.disabled = true;
    DOM.btnRunIntelligence.disabled = true;
    DOM.runStatusBadge.className = 'badge badge-cyan';
    DOM.runStatusBadge.textContent = 'EXECUTING';

    resetPipelineNodes();

    try {
        // Step 1: Animate Phase 1 Validation
        await animatePipelineStep(1, 'running', 'Phase 1: Validating input metadata & context...');
        await delay(300);

        let response;
        if (isFullExecution) {
            DOM.loadingTitle.textContent = 'EXECUTING 8-PHASE QUALITY GATEWAY';
            response = await ApiService.executeTesting(payload);
        } else {
            DOM.loadingTitle.textContent = 'EXECUTING TESTING INTELLIGENCE (P1–P3)';
            response = await ApiService.startTesting(payload);
        }

        // Check if validation passed
        if (response.validation_status !== 'passed') {
            await animatePipelineStep(1, 'failed', 'Input validation failed. Cannot proceed.');
            renderValidationErrors(response.validation_errors || []);
            DOM.resultsLoadingState.classList.add('hidden');
            DOM.runStatusBadge.className = 'badge badge-danger';
            DOM.runStatusBadge.textContent = 'VALIDATION FAILED';
            DOM.activeStageIndicator.textContent = 'FAILED';
            DOM.activeStageIndicator.className = 'stage-status-val text-danger';
            DOM.activeStageDesc.textContent = 'Phase 1 Validation Error';
            return;
        }

        await animatePipelineStep(1, 'completed');
        await animatePipelineStep(2, 'running', 'Phase 2: Extracting requirements, risks & change impact...');
        await delay(350);
        await animatePipelineStep(2, 'completed');

        await animatePipelineStep(3, 'running', 'Phase 3: Designing test cases, data & traceability...');
        await delay(350);
        await animatePipelineStep(3, 'completed');

        if (isFullExecution) {
            await animatePipelineStep(4, 'running', 'Phase 4: Executing multi-module test suites...');
            await delay(400);
            await animatePipelineStep(4, 'completed');

            await animatePipelineStep(5, 'running', 'Phase 5: Collecting concurrency telemetry & artifacts...');
            await delay(300);
            await animatePipelineStep(5, 'completed');

            await animatePipelineStep(6, 'running', 'Phase 6: Performing failure root-cause analysis...');
            await delay(350);
            await animatePipelineStep(6, 'completed');

            await animatePipelineStep(7, 'running', 'Phase 7: Evaluating 5 quality gates & quality score...');
            await delay(350);
            await animatePipelineStep(7, 'completed');

            await animatePipelineStep(8, 'running', 'Phase 8: Compiling comprehensive report & approval state...');
            await delay(300);
            await animatePipelineStep(8, 'completed');
        }

        // Store and render all phases
        storeAndRenderAllPhases(response, payload, isFullExecution);

        DOM.resultsLoadingState.classList.add('hidden');
        DOM.resultsContent.classList.remove('hidden');
        DOM.runStatusBadge.className = 'badge badge-success';
        DOM.runStatusBadge.textContent = 'COMPLETED';

        // Auto-navigate: if full execution go to Phase 7/8, if intelligence go to Phase 2
        activatePhaseTab(isFullExecution ? 'panel-phase7' : 'panel-phase2');

    } catch (e) {
        console.error('Workflow error:', e);
        DOM.resultsLoadingState.classList.add('hidden');
        DOM.validationErrorsAlert.classList.remove('hidden');
        DOM.validationErrorsList.innerHTML = `<li><strong>System Error:</strong> ${escapeHtml(e.message)}</li><li>Ensure the FastAPI backend is running on port 8085 (uvicorn app.main:app --port 8085).</li>`;
        DOM.runStatusBadge.className = 'badge badge-danger';
        DOM.runStatusBadge.textContent = 'ERROR';
    } finally {
        DOM.btnRunAll.disabled = false;
        DOM.btnRunIntelligence.disabled = false;
        if (window.lucide) lucide.createIcons();
    }
}

// ===========================================================================
// 10. PHASE DATA RENDERERS
// ===========================================================================

function storeAndRenderAllPhases(response, payload, isFullExecution) {
    // 1. Phase 1: Input Validation & Context
    renderPhase1(response, payload);

    // 2. Phase 2: Testing Intelligence
    const intel = response.intelligence || (response.report ? response.report.raw_data?.intelligence : null);
    renderPhase2(intel);

    // 3. Phase 3: Test Design
    const testDesign = response.test_design || (response.report ? response.report.raw_data?.test_design : null);
    renderPhase3(testDesign);

    // 4. Phase 4: Execution
    if (response.execution_summary || response.results) {
        renderPhase4(response.execution_summary, response.results);
    }

    // 5. Phase 5: Infrastructure
    renderPhase5(response);

    // 6. Phase 6: Result Intelligence
    renderPhase6(response.analysis);

    // 7. Phase 7: Quality Gate
    renderPhase7(response.quality_gate);

    // 8. Phase 8: Report & Approval
    renderPhase8(response.report, payload.project_id);

    // Top Status Ribbon Updates
    updateTopRibbon(response, isFullExecution);
}

function renderValidationErrors(errors) {
    DOM.validationErrorsAlert.classList.remove('hidden');
    DOM.validationErrorsList.innerHTML = '';
    errors.forEach(err => {
        const li = document.createElement('li');
        li.textContent = err;
        DOM.validationErrorsList.appendChild(li);
    });
}

function updateTopRibbon(response, isFullExecution) {
    if (isFullExecution && response.quality_gate) {
        const qg = response.quality_gate;
        DOM.activeStageIndicator.textContent = 'PHASE 8';
        DOM.activeStageIndicator.className = 'stage-status-val text-mint';
        DOM.activeStageDesc.textContent = 'Report & Governance Complete';

        DOM.headerQualityScore.textContent = (qg.quality_score != null) ? qg.quality_score.toFixed(1) : '--';
        DOM.headerQualityScore.className = `gauge-number ${(qg.quality_score >= 80) ? 'text-mint' : (qg.quality_score >= 60) ? 'text-amber' : 'text-danger'}`;

        const readiness = qg.release_readiness || 'NOT_READY';
        DOM.headerReadinessBadge.textContent = readiness;
        DOM.headerReadinessBadge.className = `readiness-pill ${(readiness === 'READY') ? 'status-ready' : (readiness === 'CONDITIONAL') ? 'status-conditional' : 'status-not-ready'}`;

        DOM.headerReleaseAllowed.innerHTML = `Release Allowed: <strong>${(readiness === 'READY' && AppState.approvalState?.approval_status === 'approved') ? 'YES' : 'NO'}</strong>`;
    } else {
        DOM.activeStageIndicator.textContent = 'PHASE 3';
        DOM.activeStageIndicator.className = 'stage-status-val text-cyan';
        DOM.activeStageDesc.textContent = 'Intelligence & Test Design Complete';
        DOM.headerQualityScore.textContent = '--';
        DOM.headerReadinessBadge.textContent = 'DESIGN STAGE';
        DOM.headerReadinessBadge.className = 'readiness-pill status-pending';
    }
}

// ---------------------------------------------------------------------------
// RENDERER: PHASE 1
// ---------------------------------------------------------------------------
function renderPhase1(response, payload) {
    const chip = document.getElementById('p1-status-chip');
    const tag = document.getElementById('p1-validation-tag');
    const body = document.getElementById('p1-validation-body');
    const jsonPre = document.getElementById('p1-context-json');

    if (chip) chip.textContent = (response.validation_status || 'PASSED').toUpperCase();
    if (tag) tag.textContent = (response.validation_status || 'PASSED').toUpperCase();

    if (body) {
        body.innerHTML = `
            <div class="check-item"><i data-lucide="check" class="text-mint"></i> <span>Project Identifier: <strong>${escapeHtml(response.project_id || payload.project_id)}</strong></span></div>
            <div class="check-item"><i data-lucide="check" class="text-mint"></i> <span>SRS Requirements Schema: Verified Valid</span></div>
            <div class="check-item"><i data-lucide="check" class="text-mint"></i> <span>SDD Architecture & Components: Verified Valid</span></div>
            <div class="check-item"><i data-lucide="check" class="text-mint"></i> <span>Source Code & Delta AST Changes: Normalized</span></div>
            <div class="check-item"><i data-lucide="check" class="text-mint"></i> <span>Validation Errors Count: 0</span></div>
        `;
    }

    if (jsonPre) {
        jsonPre.textContent = JSON.stringify({
            project_id: payload.project_id,
            srs_title: payload.srs.title,
            sdd_architecture: payload.sdd.architecture,
            repository: payload.source_code.repository,
            changed_files: payload.source_code.changes?.changed_files || [],
            context_loaded: true
        }, null, 2);
    }
}

// ---------------------------------------------------------------------------
// RENDERER: PHASE 2 (INTELLIGENCE)
// ---------------------------------------------------------------------------
function renderPhase2(intel) {
    if (!intel) return;

    // Counts
    const reqCountEl = document.getElementById('p2-reqs-count');
    const riskCountEl = document.getElementById('p2-risks-count');
    const covValEl = document.getElementById('p2-cov-val');
    if (reqCountEl) reqCountEl.textContent = (intel.requirements || []).length;
    if (riskCountEl) riskCountEl.textContent = (intel.risks || []).length;

    // 1. Requirements List
    const reqsList = document.getElementById('requirements-list');
    if (reqsList) {
        reqsList.innerHTML = '';
        (intel.requirements || []).forEach(req => {
            const card = document.createElement('div');
            card.className = 'report-card';
            card.innerHTML = `
                <div class="report-card-header">
                    <span class="report-card-id id-req">${escapeHtml(req.id)}</span>
                    <div class="badge-group">
                        <span class="inline-tag tag-cyan-border">${escapeHtml(req.category)}</span>
                        <span class="inline-tag tag-mint-border">${escapeHtml(req.source)}</span>
                    </div>
                </div>
                <p class="card-desc">${escapeHtml(req.description)}</p>
            `;
            reqsList.appendChild(card);
        });
    }

    // 2. Risks List
    const risksList = document.getElementById('risks-list');
    if (risksList) {
        risksList.innerHTML = '';
        (intel.risks || []).forEach(risk => {
            const card = document.createElement('div');
            card.className = 'report-card';
            card.style.borderColor = 'rgba(245, 158, 11, 0.3)';
            const sevClass = (risk.severity === 'High') ? 'text-danger' : (risk.severity === 'Medium') ? 'text-amber' : 'text-mint';
            card.innerHTML = `
                <div class="report-card-header">
                    <span class="report-card-id id-risk">${escapeHtml(risk.risk_id)}</span>
                    <div class="badge-group">
                        <span class="inline-tag ${sevClass}">Sev: ${escapeHtml(risk.severity)}</span>
                        <span class="inline-tag">Likelihood: ${escapeHtml(risk.likelihood)}</span>
                    </div>
                </div>
                <p class="card-desc">${escapeHtml(risk.description)}</p>
                <div class="card-mitigation-box">
                    <strong>Mitigation Blueprint:</strong> ${escapeHtml(risk.mitigation)}
                </div>
            `;
            risksList.appendChild(card);
        });
    }

    // 3. Coverage
    const cov = intel.coverage;
    if (cov) {
        const pct = (cov.coverage_percentage != null) ? cov.coverage_percentage.toFixed(1) : '0';
        if (covValEl) covValEl.textContent = `${pct}%`;
        const covPctVal = document.getElementById('coverage-percentage-val');
        if (covPctVal) covPctVal.textContent = `${pct}%`;
        const covBar = document.getElementById('coverage-progress-bar');
        if (covBar) covBar.style.width = `${pct}%`;

        const coveredTags = document.getElementById('covered-reqs-tags');
        const uncoveredTags = document.getElementById('uncovered-reqs-tags');
        if (coveredTags) {
            coveredTags.innerHTML = (cov.mapped_requirements || []).map(r => `<span class="inline-tag tag-mint-border">${escapeHtml(r)}</span>`).join('') || '<span class="inline-tag">None</span>';
        }
        if (uncoveredTags) {
            uncoveredTags.innerHTML = (cov.uncovered_requirements || []).map(r => `<span class="inline-tag text-danger">${escapeHtml(r)}</span>`).join('') || '<span class="inline-tag text-mint">None (100% Covered)</span>';
        }
    }

    // 4. Change Impact
    const impact = intel.change_impact;
    if (impact) {
        const riskLevel = impact.regression_risk || 'NONE';
        const riskBadge = document.getElementById('regression-risk-level-badge');
        if (riskBadge) {
            riskBadge.textContent = riskLevel;
            riskBadge.className = (riskLevel === 'High') ? 'risk-high' : (riskLevel === 'Medium') ? 'risk-medium' : (riskLevel === 'Low') ? 'risk-low' : 'risk-none';
        }
        const msgEl = document.getElementById('impact-message');
        if (msgEl) msgEl.textContent = impact.message;

        const filesEl = document.getElementById('impact-changed-files');
        if (filesEl) {
            filesEl.innerHTML = (impact.changed_files || []).map(f => `<li>${escapeHtml(f)}</li>`).join('') || '<li>No files modified</li>';
        }
        const funcEl = document.getElementById('impact-changed-functions');
        if (funcEl) {
            funcEl.innerHTML = (impact.changed_functions || []).map(fn => `<li>${escapeHtml(fn)}</li>`).join('') || '<li>No functions scoped</li>';
        }
        const reqTags = document.getElementById('impact-affected-reqs-tags');
        if (reqTags) {
            reqTags.innerHTML = (impact.impacted_requirements || []).map(r => `<span class="inline-tag tag-cyan-border">${escapeHtml(r)}</span>`).join('') || '<span class="inline-tag">None</span>';
        }
    }

    // 5. Strategy
    const strat = intel.test_strategy;
    if (strat) {
        const unitEl = document.getElementById('strategy-unit-tests');
        const intEl = document.getElementById('strategy-integration-tests');
        const apiEl = document.getElementById('strategy-api-tests');
        const toolsEl = document.getElementById('strategy-tools');
        const envsEl = document.getElementById('strategy-envs');

        if (unitEl) unitEl.innerHTML = (strat.unit_tests || []).map(t => `<li>${escapeHtml(t)}</li>`).join('');
        if (intEl) intEl.innerHTML = (strat.integration_tests || []).map(t => `<li>${escapeHtml(t)}</li>`).join('');
        if (apiEl) apiEl.innerHTML = (strat.api_tests || []).map(t => `<li>${escapeHtml(t)}</li>`).join('');
        if (toolsEl) toolsEl.innerHTML = (strat.tools || []).map(tool => `<span class="inline-tag tag-cyan-border">${escapeHtml(tool)}</span>`).join('');
        if (envsEl) envsEl.innerHTML = (strat.environments || []).map(env => `<span class="inline-tag tag-mint-border">${escapeHtml(env)}</span>`).join('');
    }
}

// ---------------------------------------------------------------------------
// RENDERER: PHASE 3 (TEST DESIGN)
// ---------------------------------------------------------------------------
function renderPhase3(design) {
    if (!design) return;

    AppState.cachedTestCases = design.test_cases || [];

    // Counts
    const casesCount = document.getElementById('p3-cases-count');
    const scnCount = document.getElementById('p3-scenarios-count');
    const dataCount = document.getElementById('p3-data-count');
    if (casesCount) casesCount.textContent = (design.test_cases || []).length;
    if (scnCount) scnCount.textContent = (design.test_scenarios || []).length;
    if (dataCount) dataCount.textContent = (design.generated_test_data || []).length;

    // Populate filter dropdowns
    populateFilterDropdowns(AppState.cachedTestCases);
    applyPhase3Filters();

    // Scenarios
    const scnList = document.getElementById('scenarios-list');
    if (scnList) {
        scnList.innerHTML = '';
        (design.test_scenarios || []).forEach(s => {
            const card = document.createElement('div');
            card.className = 'report-card';
            card.innerHTML = `
                <div class="report-card-header">
                    <span class="report-card-id id-scn">${escapeHtml(s.scenario_id)}</span>
                    <span class="inline-tag tag-cyan-border">${escapeHtml(s.source || 'ai_inference')}</span>
                </div>
                <h4 class="tc-title">${escapeHtml(s.title)}</h4>
                <p class="card-desc">${escapeHtml(s.description)}</p>
                <div class="tc-meta-block">
                    <span class="tc-meta-label">FLOW STEPS</span>
                    <ol class="bullet-list">${(s.flow_steps || []).map(step => `<li>${escapeHtml(step)}</li>`).join('')}</ol>
                </div>
                <div class="tc-meta-block">
                    <span class="tc-meta-label">LINKED TEST CASES</span>
                    <div class="badge-group">${(s.related_test_case_ids || []).map(tc => `<span class="inline-tag tag-mint-border">${escapeHtml(tc)}</span>`).join('')}</div>
                </div>
            `;
            scnList.appendChild(card);
        });
    }

    // Test Data Records
    const dataList = document.getElementById('test-data-list');
    if (dataList) {
        dataList.innerHTML = '';
        (design.generated_test_data || []).forEach(td => {
            const card = document.createElement('div');
            card.className = 'report-card';
            card.innerHTML = `
                <div class="report-card-header">
                    <span class="report-card-id id-td">${escapeHtml(td.data_id)}</span>
                    <span class="inline-tag tag-cyan-border">${escapeHtml(td.category)}</span>
                </div>
                <p class="card-desc">${escapeHtml(td.description)}</p>
                <div class="tc-meta-block">
                    <span class="tc-meta-label">STRUCTURED FIELDS</span>
                    <div class="json-inspector"><pre>${escapeHtml(JSON.stringify(td.fields || {}, null, 2))}</pre></div>
                </div>
            `;
            dataList.appendChild(card);
        });
    }

    // Traceability
    const trace = design.traceability;
    if (trace) {
        const uncovEl = document.getElementById('trace-uncovered-reqs');
        const orphCasesEl = document.getElementById('trace-orphaned-cases');
        const orphDataEl = document.getElementById('trace-orphaned-data');
        if (uncovEl) uncovEl.innerHTML = (trace.uncovered_requirements || []).map(r => `<span class="inline-tag">${escapeHtml(r)}</span>`).join('') || '<span class="inline-tag text-mint">None</span>';
        if (orphCasesEl) orphCasesEl.innerHTML = (trace.orphaned_test_cases || []).map(c => `<span class="inline-tag">${escapeHtml(c)}</span>`).join('') || '<span class="inline-tag text-mint">None</span>';
        if (orphDataEl) orphDataEl.innerHTML = (trace.orphaned_test_data || []).map(d => `<span class="inline-tag">${escapeHtml(d)}</span>`).join('') || '<span class="inline-tag text-mint">None</span>';

        const traceList = document.getElementById('traceability-list');
        if (traceList) {
            traceList.innerHTML = '';
            (trace.entries || []).forEach(e => {
                const card = document.createElement('div');
                card.className = 'report-card';
                card.innerHTML = `
                    <div class="trace-chain-row">
                        <div class="trace-chain-node"><span class="trace-chain-label">REQ</span><span class="trace-chain-value id-req">${escapeHtml(e.requirement_id)}</span></div>
                        <span class="trace-chain-arrow">➔</span>
                        <div class="trace-chain-node"><span class="trace-chain-label">RSK</span><span class="trace-chain-value id-risk">${escapeHtml(e.risk_id || 'N/A')}</span></div>
                        <span class="trace-chain-arrow">➔</span>
                        <div class="trace-chain-node"><span class="trace-chain-label">SCN</span><span class="trace-chain-value id-scn">${escapeHtml(e.scenario_id)}</span></div>
                        <span class="trace-chain-arrow">➔</span>
                        <div class="trace-chain-node"><span class="trace-chain-label">TC</span><span class="trace-chain-value id-tc">${escapeHtml(e.test_case_id)}</span></div>
                    </div>
                `;
                traceList.appendChild(card);
            });
        }
    }
}

function populateFilterDropdowns(testCases) {
    const typeSelect = document.getElementById('filter-test-type');
    const prioSelect = document.getElementById('filter-priority');
    const catSelect = document.getElementById('filter-category');

    const types = [...new Set(testCases.map(t => t.test_type).filter(Boolean))];
    const prios = [...new Set(testCases.map(t => t.priority).filter(Boolean))];
    const cats = [...new Set(testCases.map(t => t.test_category).filter(Boolean))];

    if (typeSelect) {
        typeSelect.innerHTML = '<option value="all">All Types</option>' + types.map(t => `<option value="${t}">${t.toUpperCase()}</option>`).join('');
    }
    if (prioSelect) {
        prioSelect.innerHTML = '<option value="all">All Priorities</option>' + prios.map(p => `<option value="${p}">${p}</option>`).join('');
    }
    if (catSelect) {
        catSelect.innerHTML = '<option value="all">All Categories</option>' + cats.map(c => `<option value="${c}">${c}</option>`).join('');
    }
}

function applyPhase3Filters() {
    const list = document.getElementById('test-cases-list');
    if (!list) return;
    list.innerHTML = '';

    const filtered = AppState.cachedTestCases.filter(tc => {
        if (AppState.selectedTestType !== 'all' && tc.test_type !== AppState.selectedTestType) return false;
        if (AppState.selectedPriority !== 'all' && tc.priority !== AppState.selectedPriority) return false;
        if (AppState.selectedCategory !== 'all' && tc.test_category !== AppState.selectedCategory) return false;
        return true;
    });

    if (filtered.length === 0) {
        list.innerHTML = '<div class="report-card"><span class="card-desc">No test cases match the selected filters.</span></div>';
        return;
    }

    filtered.forEach(tc => {
        const card = document.createElement('div');
        card.className = 'report-card tc-card';
        const prioClass = (tc.priority === 'High') ? 'text-danger' : (tc.priority === 'Medium') ? 'text-amber' : 'text-mint';
        card.innerHTML = `
            <div class="report-card-header">
                <span class="report-card-id id-tc">${escapeHtml(tc.test_case_id)}</span>
                <div class="badge-group">
                    <span class="inline-tag tag-cyan-border">${escapeHtml((tc.test_type || '').toUpperCase())}</span>
                    <span class="inline-tag ${prioClass}">Prio: ${escapeHtml(tc.priority)}</span>
                    <span class="inline-tag">${escapeHtml(tc.test_category)}</span>
                </div>
            </div>
            <h4 class="tc-title">${escapeHtml(tc.title)}</h4>
            <p class="card-desc">${escapeHtml(tc.description)}</p>
            <div class="tc-expandable-details">
                <div class="tc-meta-block">
                    <span class="tc-meta-label">EXPECTED RESULT</span>
                    <div style="color: var(--mint); font-weight: 600;">${escapeHtml(tc.expected_result)}</div>
                </div>
                <div class="tc-meta-block">
                    <span class="tc-meta-label">STEPS</span>
                    <ol class="bullet-list">${(tc.steps || []).map(s => `<li>${escapeHtml(s)}</li>`).join('')}</ol>
                </div>
                <div class="tc-meta-block">
                    <span class="tc-meta-label">ASSERTIONS</span>
                    <ul class="bullet-list">${(tc.assertions || []).map(a => `<li>${escapeHtml(a)}</li>`).join('')}</ul>
                </div>
            </div>
        `;
        list.appendChild(card);
    });
}

// ---------------------------------------------------------------------------
// RENDERER: PHASE 4 (TEST EXECUTION)
// ---------------------------------------------------------------------------
function renderPhase4(summary = {}, results = []) {
    const chip = document.getElementById('p4-status-chip');
    if (chip) chip.textContent = 'COMPLETED';

    // Summary numbers
    const total = summary.total ?? results.length;
    const passed = summary.passed ?? results.filter(r => (r.status || '').toUpperCase() === 'PASS').length;
    const failed = (summary.failed ?? 0) + (summary.errors ?? 0);
    const skipped = summary.skipped ?? results.filter(r => (r.status || '').toUpperCase() === 'SKIPPED').length;
    const passRate = total > 0 ? ((passed / total) * 100).toFixed(1) : '0.0';

    document.getElementById('execution-total').textContent = total;
    document.getElementById('execution-passed').textContent = passed;
    document.getElementById('execution-failed').textContent = failed;
    document.getElementById('execution-skipped').textContent = skipped;
    document.getElementById('execution-pass-rate').textContent = `${passRate}%`;
    document.getElementById('execution-duration').textContent = summary.duration ? `${summary.duration.toFixed(2)}s` : `${results.reduce((acc, r) => acc + (r.duration || 0), 0).toFixed(2)}s`;

    // Modules
    const modulesContainer = document.getElementById('execution-module-overview');
    if (modulesContainer) {
        modulesContainer.innerHTML = '';
        const modules = [...new Set(results.map(r => r.module).filter(Boolean))];
        modules.forEach(mod => {
            const modResults = results.filter(r => r.module === mod);
            const modPassed = modResults.filter(r => (r.status || '').toUpperCase() === 'PASS').length;
            const card = document.createElement('div');
            card.className = 'report-card';
            card.innerHTML = `
                <div class="report-card-header">
                    <span class="report-card-id">${escapeHtml(mod.toUpperCase())} MODULE</span>
                    <span class="inline-tag tag-cyan-border">${modPassed}/${modResults.length} Passed</span>
                </div>
                <div class="card-desc">Executed via execution controller module runner.</div>
            `;
            modulesContainer.appendChild(card);
        });
    }

    // Results table / cards
    const resultsContainer = document.getElementById('execution-results-container');
    if (resultsContainer) {
        resultsContainer.innerHTML = '';
        results.forEach(r => {
            const st = (r.status || 'UNKNOWN').toUpperCase();
            const card = document.createElement('div');
            card.className = `report-card exec-card ${(st === 'PASS') ? 'pass' : (st === 'SKIPPED') ? 'skipped' : 'fail'}`;
            const stTagClass = (st === 'PASS') ? 'tag-mint-border' : (st === 'SKIPPED') ? 'tag-amber-border' : 'text-danger';

            card.innerHTML = `
                <div class="report-card-header">
                    <span class="report-card-id">${escapeHtml(r.test_case_id)}</span>
                    <div class="badge-group">
                        <span class="inline-tag ${stTagClass}">${st}</span>
                        <span class="inline-tag">${escapeHtml(r.module || 'unit')}</span>
                        <span class="inline-tag text-mono">${r.duration != null ? r.duration.toFixed(3) + 's' : '--'}</span>
                    </div>
                </div>
                <h4 class="tc-title">${escapeHtml(r.name || 'Test Case')}</h4>
                <p class="card-desc">${escapeHtml(r.details || 'Execution completed without assertion errors.')}</p>
                <div class="execution-details">
                    <div class="tc-meta-label">EXECUTION LOG TRACE</div>
                    <div class="execution-logs">
                        <pre>${escapeHtml((r.logs || []).map(l => (typeof l === 'object' ? JSON.stringify(l, null, 2) : l)).join('\n') || 'Log trail: execution successful')}</pre>
                    </div>
                </div>
            `;
            resultsContainer.appendChild(card);
        });
    }
}

// ---------------------------------------------------------------------------
// RENDERER: PHASE 5 (INFRASTRUCTURE)
// ---------------------------------------------------------------------------
function renderPhase5(response) {
    const chip = document.getElementById('p5-status-chip');
    if (chip) chip.textContent = 'RECORDED';

    document.getElementById('infra-run-id').textContent = `RUN-ID: ${response.run_id || 'run-local-001'}`;
    document.getElementById('infra-platform').textContent = response.platform || 'Windows 64-bit (x86_64)';
    document.getElementById('infra-python').textContent = response.python_version || 'Python 3.14.6';
    document.getElementById('infra-workers').textContent = `${response.max_workers || 4} Concurrency Threads`;
    document.getElementById('infra-retries').textContent = `Max Retries: ${response.max_retries || 2}`;
    document.getElementById('infra-started').textContent = response.started_at || new Date().toISOString();
    document.getElementById('infra-completed').textContent = response.completed_at || new Date().toISOString();

    // Artifacts & Screenshots
    const artifactsContainer = document.getElementById('infra-artifacts-container');
    if (artifactsContainer) {
        artifactsContainer.innerHTML = '';
        const results = response.results || [];
        const screenshots = results.filter(r => r.screenshot);

        if (screenshots.length === 0) {
            artifactsContainer.innerHTML = '<div class="report-card"><span class="card-desc">No visual screenshot failures captured (headless unit/api execution).</span></div>';
        } else {
            screenshots.forEach(sc => {
                const card = document.createElement('div');
                card.className = 'report-card artifact-card-img';
                card.innerHTML = `
                    <div class="report-card-header">
                        <span class="report-card-id">${escapeHtml(sc.test_case_id)}</span>
                        <span class="inline-tag text-danger">FAILURE SCREENSHOT</span>
                    </div>
                    <img src="${sc.screenshot}" alt="Evidence">
                `;
                card.onclick = () => openScreenshotModal(sc.screenshot, sc.test_case_id);
                artifactsContainer.appendChild(card);
            });
        }
    }
}

// ---------------------------------------------------------------------------
// RENDERER: PHASE 6 (FAILURE ANALYSIS)
// ---------------------------------------------------------------------------
function renderPhase6(analysis) {
    const chip = document.getElementById('p6-status-chip');
    if (!analysis) {
        if (chip) chip.textContent = 'CLEAN';
        return;
    }
    if (chip) chip.textContent = 'ANALYZED';

    document.getElementById('p6-total-failures').textContent = analysis.total_failures || (analysis.failures || []).length;
    document.getElementById('p6-product-defects').textContent = (analysis.defects || []).filter(d => (d.classification || '').includes('product')).length;
    document.getElementById('p6-test-defects').textContent = (analysis.defects || []).filter(d => !(d.classification || '').includes('product')).length;
    document.getElementById('p6-flaky-tests').textContent = (analysis.flaky_tests || []).length;

    // 1. Failures
    const failList = document.getElementById('p6-failures-list');
    if (failList) {
        failList.innerHTML = '';
        (analysis.failures || []).forEach(f => {
            const card = document.createElement('div');
            card.className = 'report-card alert-danger';
            card.innerHTML = `
                <div class="report-card-header">
                    <span class="report-card-id text-danger">${escapeHtml(f.test_case_id)}</span>
                    <span class="inline-tag text-danger">${escapeHtml(f.failure_type)}</span>
                </div>
                <h4 class="tc-title">${escapeHtml(f.failure_summary)}</h4>
                <p class="card-desc"><strong>Observed:</strong> ${escapeHtml(f.observed_behavior || 'Assertion failure occurred')}</p>
                <div class="tc-meta-block">
                    <span class="tc-meta-label">RAW EVIDENCE</span>
                    <div class="json-inspector"><pre>${escapeHtml((f.evidence || []).join('\n'))}</pre></div>
                </div>
            `;
            failList.appendChild(card);
        });
    }

    // 2. Root causes
    const rcList = document.getElementById('p6-rootcauses-list');
    if (rcList) {
        rcList.innerHTML = '';
        (analysis.root_causes || []).forEach(rc => {
            const card = document.createElement('div');
            card.className = 'report-card';
            card.innerHTML = `
                <div class="report-card-header">
                    <span class="report-card-id">${escapeHtml(rc.test_case_id)}</span>
                    <span class="inline-tag tag-amber-border">Category: ${escapeHtml(rc.category)}</span>
                </div>
                <h4 class="tc-title">${escapeHtml(rc.summary)}</h4>
                <p class="card-desc">${escapeHtml(rc.explanation)}</p>
                <span class="inline-tag tag-mint-border" style="margin-top: 8px;">Confidence: ${escapeHtml(rc.confidence)}</span>
            `;
            rcList.appendChild(card);
        });
    }

    // 3. Defects
    const defectList = document.getElementById('p6-defects-list');
    if (defectList) {
        defectList.innerHTML = '';
        (analysis.defects || []).forEach(d => {
            const card = document.createElement('div');
            card.className = 'report-card';
            const sevClass = (d.severity === 'critical' || d.severity === 'high') ? 'text-danger' : 'text-amber';
            card.innerHTML = `
                <div class="report-card-header">
                    <span class="report-card-id ${sevClass}">${escapeHtml(d.test_case_id)}</span>
                    <div class="badge-group">
                        <span class="inline-tag ${sevClass}">Sev: ${escapeHtml((d.severity || '').toUpperCase())}</span>
                        <span class="inline-tag tag-cyan-border">Prio: ${escapeHtml(d.priority || 'P1')}</span>
                    </div>
                </div>
                <h4 class="tc-title">${escapeHtml(d.summary)}</h4>
                <p class="card-desc"><strong>Classification:</strong> ${escapeHtml(d.classification)}</p>
                <div class="card-mitigation-box">
                    <strong>Triage Action:</strong> ${escapeHtml(d.triage_recommendation || 'Remediate in source code.')}
                </div>
            `;
            defectList.appendChild(card);
        });
    }

    // 4. Flaky
    const flakyList = document.getElementById('p6-flaky-list');
    if (flakyList) {
        flakyList.innerHTML = '';
        if ((analysis.flaky_tests || []).length === 0) {
            flakyList.innerHTML = '<div class="report-card"><span class="card-desc">Zero flaky tests detected across execution attempts.</span></div>';
        } else {
            (analysis.flaky_tests || []).forEach(fl => {
                const card = document.createElement('div');
                card.className = 'report-card';
                card.innerHTML = `
                    <div class="report-card-header">
                        <span class="report-card-id">${escapeHtml(fl.test_case_id)}</span>
                        <span class="inline-tag tag-amber-border">Score: ${fl.flakiness_score}</span>
                    </div>
                    <p class="card-desc">${escapeHtml(fl.reason)}</p>
                `;
                flakyList.appendChild(card);
            });
        }
    }
}

// ---------------------------------------------------------------------------
// RENDERER: PHASE 7 (QUALITY GATE & RELEASE READINESS)
// ---------------------------------------------------------------------------
function renderPhase7(qg) {
    if (!qg) return;
    const chip = document.getElementById('p7-status-chip');
    if (chip) chip.textContent = qg.overall_status || 'EVALUATED';

    const scoreNum = document.getElementById('qg-score-num');
    const readTag = document.getElementById('qg-readiness-tag');
    const overallBadge = document.getElementById('qg-overall-badge');

    if (scoreNum) scoreNum.textContent = (qg.quality_score != null) ? qg.quality_score.toFixed(1) : '0.0';
    if (readTag) {
        readTag.textContent = qg.release_readiness || 'NOT_READY';
        readTag.className = `readiness-tag ${(qg.release_readiness === 'READY') ? 'status-ready' : (qg.release_readiness === 'CONDITIONAL') ? 'status-conditional' : 'status-not-ready'}`;
    }
    if (overallBadge) overallBadge.textContent = qg.overall_status || 'PASS';

    // Components formula table
    const table = document.getElementById('qg-components-table');
    if (table && qg.score_breakdown && qg.score_breakdown.components) {
        table.innerHTML = '';
        Object.entries(qg.score_breakdown.components).forEach(([name, comp]) => {
            const row = document.createElement('div');
            row.className = 'score-row';
            row.innerHTML = `
                <span class="score-row-name">${escapeHtml(name.replace('_', ' ').toUpperCase())}</span>
                <span class="score-row-weight">Weight: ${(comp.weight * 100).toFixed(0)}%</span>
                <span class="score-row-pts">${comp.points != null ? comp.points.toFixed(1) : '--'} pts</span>
            `;
            table.appendChild(row);
        });
    }

    // 5 Quality Gate Cards
    const gatesContainer = document.getElementById('qg-5-gates-container');
    if (gatesContainer) {
        gatesContainer.innerHTML = '';
        const gates = [
            { name: 'Execution Gate', g: qg.execution_gate },
            { name: 'Requirements Coverage Gate', g: qg.coverage_gate },
            { name: 'Software Risk Gate', g: qg.risk_gate },
            { name: 'Defect Severity Gate', g: qg.defect_gate },
            { name: 'Flaky Tests Gate', g: qg.flaky_gate }
        ];

        gates.forEach(({ name, g }) => {
            if (!g) return;
            const st = (g.status || 'NOT_EVALUATED').toUpperCase();
            const cardClass = (st === 'PASS') ? 'gate-pass' : (st === 'FAIL') ? 'gate-fail' : 'gate-cond';
            const card = document.createElement('div');
            card.className = `gate-card-item ${cardClass}`;
            card.innerHTML = `
                <div class="report-card-header">
                    <span class="report-card-id">${escapeHtml(name)}</span>
                    <span class="inline-tag ${(st === 'PASS') ? 'tag-mint-border' : (st === 'FAIL') ? 'text-danger' : 'tag-amber-border'}">${st}</span>
                </div>
                <p class="card-desc">${escapeHtml(g.summary || 'Gate evaluation completed.')}</p>
                <div class="tc-meta-block">
                    <span class="tc-meta-label">OBSERVED METRICS</span>
                    <div class="json-inspector"><pre>${escapeHtml(JSON.stringify(g.metrics || {}, null, 2))}</pre></div>
                </div>
            `;
            gatesContainer.appendChild(card);
        });
    }

    // Blocking issues
    const blockList = document.getElementById('qg-blocking-issues-list');
    if (blockList) {
        blockList.innerHTML = (qg.blocking_issues || []).map(i => `<li>${escapeHtml(i)}</li>`).join('') || '<li>Zero blocking release issues detected.</li>';
    }
    const recList = document.getElementById('qg-recommendations-list');
    if (recList) {
        recList.innerHTML = (qg.recommendations || []).map(r => `<li>${escapeHtml(r)}</li>`).join('') || '<li>All testing conditions satisfied for release.</li>';
    }
}

// ---------------------------------------------------------------------------
// RENDERER: PHASE 8 (REPORTS & HUMAN APPROVAL)
// ---------------------------------------------------------------------------
function renderPhase8(report, projectId) {
    const chip = document.getElementById('p8-status-chip');
    if (chip) chip.textContent = 'REPORT GENERATED';

    AppState.currentReport = report;

    if (report) {
        const execSummary = document.getElementById('report-exec-summary');
        if (execSummary) execSummary.textContent = report.executive_summary || 'All test suites executed and audited.';

        const phasesGrid = document.getElementById('report-phases-grid');
        if (phasesGrid) {
            phasesGrid.innerHTML = '';
            (report.phases || []).forEach(p => {
                const card = document.createElement('div');
                card.className = 'report-card';
                card.innerHTML = `
                    <div class="report-card-header">
                        <span class="report-card-id">Phase ${p.phase_number}: ${escapeHtml(p.phase_name)}</span>
                        <span class="inline-tag tag-mint-border">${(p.status || '').toUpperCase()}</span>
                    </div>
                    <p class="card-desc">${escapeHtml(p.summary)}</p>
                `;
                phasesGrid.appendChild(card);
            });
        }
    }

    // Check Approval Status from backend
    fetchAndRenderApprovalStatus(projectId);
}

// ===========================================================================
// 11. HUMAN APPROVAL & REJECTION WORKFLOW
// ===========================================================================

async function fetchAndRenderApprovalStatus(projectId) {
    try {
        const approval = await ApiService.getApprovalStatus(projectId);
        if (approval) {
            AppState.approvalState = approval;
            updateApprovalCard(approval);
        }
    } catch (e) {
        console.error('Failed to get approval status:', e);
    }
}

function updateApprovalCard(approval) {
    const badge = document.getElementById('approval-status-badge');
    const qgStatus = document.getElementById('approval-qg-status');
    const readiness = document.getElementById('approval-readiness');
    const allowed = document.getElementById('approval-release-allowed');
    const reviewer = document.getElementById('approval-reviewer-name');
    const timestamp = document.getElementById('approval-timestamp-val');
    const reportRef = document.getElementById('approval-report-ref');
    const commentBox = document.getElementById('approval-comment-box');
    const commentContent = document.getElementById('approval-comment-content');

    const status = (approval.approval_status || 'pending').toUpperCase();

    if (badge) {
        badge.textContent = status;
        badge.className = `approval-badge-large ${(status === 'APPROVED') ? 'approved' : (status === 'REJECTED') ? 'rejected' : ''}`;
    }

    if (qgStatus) qgStatus.textContent = approval.quality_gate_status || '--';
    if (readiness) readiness.textContent = approval.release_readiness || '--';
    if (allowed) {
        allowed.textContent = approval.release_allowed ? 'YES' : 'NO';
        allowed.className = `cell-value ${approval.release_allowed ? 'text-mint' : 'text-danger'}`;
    }

    if (reviewer) reviewer.textContent = approval.approved_by || '--';
    if (timestamp) timestamp.textContent = approval.approval_timestamp || '--';
    if (reportRef) reportRef.textContent = approval.report_id || 'RPT-LATEST';

    if (commentBox && commentContent) {
        if (approval.comment) {
            commentBox.classList.remove('hidden');
            commentContent.textContent = approval.comment;
        } else {
            commentBox.classList.add('hidden');
        }
    }

    // Sync header ribbon
    DOM.headerApprovalStatus.textContent = status;
    DOM.headerApprovalStatus.className = `approval-status-tag ${(status === 'APPROVED') ? 'status-ready' : (status === 'REJECTED') ? 'status-not-ready' : 'status-pending'}`;
    DOM.headerApprovalReviewer.innerHTML = `Reviewer: <strong>${escapeHtml(approval.approved_by || '--')}</strong>`;
}

function wireApprovalActions() {
    const btnApprove = document.getElementById('btn-action-approve');
    const btnReject = document.getElementById('btn-action-reject');
    const rejectionForm = document.getElementById('rejection-form-container');
    const btnCancelRejection = document.getElementById('btn-cancel-rejection');
    const btnConfirmRejection = document.getElementById('btn-confirm-rejection');

    // Approve Release -> open modal
    if (btnApprove) {
        btnApprove.addEventListener('click', () => {
            DOM.reviewerIdInput.value = '';
            DOM.reviewerNotesInput.value = '';
            DOM.modalReviewer.classList.remove('hidden');
        });
    }

    // Submit Approval from Modal
    if (DOM.btnSubmitApproval) {
        DOM.btnSubmitApproval.addEventListener('click', async () => {
            const reviewer = DOM.reviewerIdInput.value.trim();
            const notes = DOM.reviewerNotesInput.value.trim();
            if (!reviewer) {
                alert('Reviewer identifier is required to sign off release');
                return;
            }

            try {
                const res = await ApiService.approveReport({
                    project_id: AppState.currentProjectId,
                    report_id: AppState.currentReport?.report_id || `RPT-${AppState.currentProjectId}`,
                    approved_by: reviewer,
                    comment: notes || null
                });
                DOM.modalReviewer.classList.add('hidden');
                AppState.approvalState = res;
                updateApprovalCard(res);
                alert(`✅ Release Approved successfully by ${reviewer}!`);
            } catch (e) {
                alert(`Approval failed: ${e.message}`);
            }
        });
    }

    // Reject Release -> reveal form
    if (btnReject) {
        btnReject.addEventListener('click', () => {
            rejectionForm.classList.remove('hidden');
        });
    }

    if (btnCancelRejection) {
        btnCancelRejection.addEventListener('click', () => {
            rejectionForm.classList.add('hidden');
        });
    }

    if (btnConfirmRejection) {
        btnConfirmRejection.addEventListener('click', async () => {
            const reason = document.getElementById('rejection-reason-input').value.trim();
            if (!reason) {
                alert('A mandatory rejection reason is required');
                return;
            }

            const reviewer = prompt('Enter Reviewer Name / Identity for rejection sign-off:');
            if (!reviewer || !reviewer.trim()) {
                alert('Reviewer name is required');
                return;
            }

            try {
                const res = await ApiService.rejectReport({
                    project_id: AppState.currentProjectId,
                    report_id: AppState.currentReport?.report_id || `RPT-${AppState.currentProjectId}`,
                    approved_by: reviewer.trim(),
                    comment: reason
                });
                rejectionForm.classList.add('hidden');
                AppState.approvalState = res;
                updateApprovalCard(res);
                alert(`❌ Release Rejected by ${reviewer.trim()}. Deployment has been blocked.`);
            } catch (e) {
                alert(`Rejection failed: ${e.message}`);
            }
        });
    }
}

// ===========================================================================
// 12. REPORT EXPORTS (PDF, DOCX, MD, JSON, HTML, CSV)
// ===========================================================================

function wireReportExports() {
    const btnPdf = document.getElementById('btn-export-pdf');
    const btnDocx = document.getElementById('btn-export-docx');
    const btnMd = document.getElementById('btn-export-md');
    const btnJson = document.getElementById('btn-export-json');
    const btnHtml = document.getElementById('btn-export-html');
    const btnCsv = document.getElementById('btn-export-csv');

    if (btnPdf) {
        btnPdf.addEventListener('click', async () => {
            try {
                const payload = compilePayload();
                const blob = await ApiService.exportReportBlob(payload, 'pdf');
                if (blob) downloadBlob(blob, `testing-report-${AppState.currentProjectId}.pdf`);
            } catch (e) {
                alert(`Export PDF error: ${e.message}`);
            }
        });
    }

    if (btnDocx) {
        btnDocx.addEventListener('click', async () => {
            try {
                const payload = compilePayload();
                const blob = await ApiService.exportReportBlob(payload, 'docx');
                if (blob) downloadBlob(blob, `testing-report-${AppState.currentProjectId}.docx`);
            } catch (e) {
                alert(`Export DOCX error: ${e.message}`);
            }
        });
    }

    if (btnMd) {
        btnMd.addEventListener('click', async () => {
            try {
                const payload = compilePayload();
                const blob = await ApiService.exportReportBlob(payload, 'md');
                if (blob) downloadBlob(blob, `testing-report-${AppState.currentProjectId}.md`);
            } catch (e) {
                alert(`Export MD error: ${e.message}`);
            }
        });
    }

    if (btnJson) {
        btnJson.addEventListener('click', () => {
            const reportData = AppState.currentReport || { project_id: AppState.currentProjectId, status: 'completed' };
            const blob = new Blob([JSON.stringify(reportData, null, 2)], { type: 'application/json' });
            downloadBlob(blob, `testing-report-${AppState.currentProjectId}.json`);
        });
    }

    if (btnHtml) {
        btnHtml.addEventListener('click', async () => {
            try {
                const payload = compilePayload();
                const blob = await ApiService.exportReportBlob(payload, 'html');
                if (blob) downloadBlob(blob, `testing-report-${AppState.currentProjectId}.html`);
            } catch (e) {
                alert(`Export HTML error: ${e.message}`);
            }
        });
    }

    if (btnCsv) {
        btnCsv.addEventListener('click', async () => {
            try {
                const payload = compilePayload();
                const blob = await ApiService.exportReportBlob(payload, 'csv');
                if (blob) downloadBlob(blob, `testing-report-${AppState.currentProjectId}.csv`);
            } catch (e) {
                alert(`Export CSV error: ${e.message}`);
            }
        });
    }
}

function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// ===========================================================================
// 13. MODALS & UTILITIES
// ===========================================================================

function wireModals() {
    if (DOM.btnCancelApproval) DOM.btnCancelApproval.onclick = () => DOM.modalReviewer.classList.add('hidden');
    if (DOM.btnCloseReviewerModal) DOM.btnCloseReviewerModal.onclick = () => DOM.modalReviewer.classList.add('hidden');
    if (DOM.btnCloseScreenshotModal) DOM.btnCloseScreenshotModal.onclick = () => DOM.modalScreenshot.classList.add('hidden');
}

function openScreenshotModal(src, title) {
    DOM.modalScreenshotImg.src = src;
    DOM.modalScreenshotTitle.textContent = `Screenshot Evidence — ${title}`;
    DOM.modalScreenshot.classList.remove('hidden');
}

function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
