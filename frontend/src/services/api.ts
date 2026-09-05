export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api';
export const API_KEY = import.meta.env.VITE_STUDIO_API_KEY || 'default_secret_key_12345';

export const apiFetch = async (url: string, options: RequestInit = {}): Promise<Response> => {
  const headers = new Headers(options.headers || {});
  if (!headers.has('X-API-Key')) {
    headers.set('X-API-Key', API_KEY);
  }
  return fetch(url, {
    ...options,
    headers,
  });
};

export interface Project {
  id: string;
  name: string;
  description?: string;
  current_phase: string;
  status: string;
  created_at: string;
}

export interface RequirementMemory {
  project_summary?: string;
  business_goals?: string;
  target_users: string[];
  functional_requirements: string[];
  non_functional_requirements: string[];
  constraints: string[];
  assumptions: string[];
  acceptance_criteria: string[];
  open_questions: string[];
}

export interface TraceabilityItem {
  id: string;
  title: string;
  description: string;
  category: string;
}

export interface SRSOutput {
  project_name: string;
  project_summary: string;
  business_objectives: string;
  scope: string;
  epics: string[];
  features: string[];
  user_stories: string[];
  functional_requirements: string[];
  non_functional_requirements: string[];
  acceptance_criteria: string[];
  assumptions: string[];
  constraints: string[];
  risks: string[];
  traceability_metadata: TraceabilityItem[];
}

export interface Log {
  action: string;
  details?: string;
  timestamp: string;
}

export interface ProjectStatusResponse {
  project: Project;
  agent_state: {
    messages: { sender: 'user' | 'agent'; text: string; timestamp?: string }[];
    memory: RequirementMemory;
    phase: string;
    missing_info: string[];
    validation_attempts: number;
    document?: any;
  };
  design_agent_state?: any;
  srs: SRSOutput | null;
  sdd?: any | null;
  logs: Log[];
}

export const api = {
  async listProjects(): Promise<Project[]> {
    const res = await apiFetch(`${API_BASE}/projects`);
    if (!res.ok) throw new Error('Failed to load projects');
    return res.json();
  },

  async createProject(name: string, description: string): Promise<Project> {
    const res = await apiFetch(`${API_BASE}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description })
    });
    if (!res.ok) throw new Error('Failed to create project');
    return res.json();
  },

  async getProjectStatus(projectId: string): Promise<ProjectStatusResponse> {
    const res = await apiFetch(`${API_BASE}/projects/${projectId}/status`);
    if (!res.ok) throw new Error('Failed to load project status');
    return res.json();
  },

  async sendMessage(projectId: string, message: string) {
    const res = await apiFetch(`${API_BASE}/projects/${projectId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message })
    });
    if (!res.ok) throw new Error('Failed to send message');
    return res.json();
  },

  async submitReview(projectId: string, status: 'APPROVED' | 'REJECTED' | 'REQUEST_CHANGES', comments: string, reviewerName: string = "Lead Architect", stage?: string) {
    const url = `${API_BASE}/projects/${projectId}/requirements/${status === 'APPROVED' ? 'approve' : 'reject'}`;
    const res = await apiFetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, comments, reviewer_name: reviewerName, stage })
    });
    if (!res.ok) throw new Error('Failed to submit review');
    return res.json();
  },

  async getVersionHistory(projectId: string) {
    const res = await apiFetch(`${API_BASE}/projects/${projectId}/history`);
    if (!res.ok) throw new Error('Failed to load history');
    return res.json();
  },

  async generateDesign(projectId: string) {
    const res = await apiFetch(`${API_BASE}/projects/${projectId}/design/generate`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Failed to start design generation');
    return res.json();
  },

  async submitDesignReview(projectId: string, status: 'APPROVED' | 'REJECTED' | 'REQUEST_CHANGES', comments: string, reviewerName: string = "Lead Architect", stage?: string) {
    const url = `${API_BASE}/projects/${projectId}/design/${status === 'APPROVED' ? 'approve' : 'reject'}`;
    const res = await apiFetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, comments, reviewer_name: reviewerName, stage })
    });
    if (!res.ok) throw new Error('Failed to submit design review');
    return res.json();
  },

  async getDesignHistory(projectId: string) {
    const res = await apiFetch(`${API_BASE}/projects/${projectId}/design/versions`);
    if (!res.ok) throw new Error('Failed to load design history');
    return res.json();
  },

  async uploadRequirementDocument(projectId: string, file: File): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    const res = await apiFetch(`${API_BASE}/projects/${projectId}/requirements/upload`, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) throw new Error('Failed to upload document');
    return res.json();
  },

  async getTestCases(projectId: string, type?: string) {
    const query = type ? `?type=${type}` : '';
    const res = await apiFetch(`${API_BASE}/projects/${projectId}/development/tests${query}`);
    if (!res.ok) throw new Error('Failed to load test cases');
    return res.json();
  },

  async getTestReport(projectId: string) {
    const res = await apiFetch(`${API_BASE}/projects/${projectId}/development/tests/report`);
    if (!res.ok) throw new Error('Failed to load test report');
    return res.json();
  },

  downloadTestReportPdfUrl(projectId: string): string {
    return `${API_BASE}/projects/${projectId}/development/tests/download/pdf?api_key=${API_KEY}`;
  },

  async getTestingPayload(projectId: string) {
    const res = await apiFetch(`${API_BASE}/projects/${projectId}/testing/payload`);
    if (!res.ok) throw new Error('Failed to load testing payload');
    return res.json();
  },

  async startTesting(projectId: string) {
    const res = await apiFetch(`${API_BASE}/projects/${projectId}/testing/start`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Failed to start testing intelligence');
    return res.json();
  },

  async executeTesting(projectId: string, testCaseIds?: string[]) {
    const options: RequestInit = {
      method: 'POST'
    };
    if (testCaseIds && testCaseIds.length > 0) {
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify({ test_case_ids: testCaseIds });
    }
    const res = await apiFetch(`${API_BASE}/projects/${projectId}/testing/execute`, options);
    if (!res.ok) throw new Error('Failed to execute testing pipeline');
    return res.json();
  },

  async retryFailedTests(projectId: string, testCaseIds?: string[]) {
    const options: RequestInit = {
      method: 'POST'
    };
    if (testCaseIds && testCaseIds.length > 0) {
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify({ test_case_ids: testCaseIds });
    }
    const res = await apiFetch(`${API_BASE}/projects/${projectId}/testing/retry`, options);
    if (!res.ok) throw new Error('Failed to retry test cases');
    return res.json();
  },

  async getTestingStatus(projectId: string) {
    const res = await apiFetch(`${API_BASE}/projects/${projectId}/testing/status`);
    if (!res.ok) throw new Error('Failed to fetch testing status');
    return res.json();
  },

  async approveTesting(projectId: string, reportId: string, approvedBy: string, comment: string) {
    const res = await apiFetch(`${API_BASE}/projects/${projectId}/testing/report/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_id: reportId, approved_by: approvedBy, comment })
    });
    if (!res.ok) throw new Error('Failed to approve testing report');
    return res.json();
  },

  async rejectTesting(projectId: string, reportId: string, approvedBy: string, comment: string) {
    const res = await apiFetch(`${API_BASE}/projects/${projectId}/testing/report/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_id: reportId, approved_by: approvedBy, comment })
    });
    if (!res.ok) throw new Error('Failed to reject testing report');
    return res.json();
  },

  async downloadReport(projectId: string, format: string) {
    const res = await apiFetch(`${API_BASE}/projects/${projectId}/testing/export/${format}`);
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Failed to download report as ${format.toUpperCase()}: ${errText}`);
    }
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `test-report-${projectId}.${format}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  }
};

export interface TestCase {
  id: string;
  test_case_id: string;
  module: string;
  test_type: 'Unit' | 'Integration' | 'API' | 'Functional' | 'Security' | 'Regression';
  name: string;
  test_scenario: string;
  preconditions: string;
  test_steps: string;
  test_input: string;
  expected_result: string;
  actual_result: string;
  status: 'PASS' | 'FAIL' | 'PASSED' | 'FAILED' | 'SKIPPED';
  duration: number;
  error_details?: string;
  error_message?: string;
  source_snippet?: string;
  created_at: string;
}

export interface TestCategorySummary {
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  cases: TestCase[];
}



