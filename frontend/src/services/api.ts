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
  }
};

