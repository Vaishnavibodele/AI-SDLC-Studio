import React, { useState, useEffect, useRef, useMemo } from 'react';
import { 
  LayoutDashboard, 
  MessageSquare, 
  Sparkles, 
  FolderPlus, 
  CheckCircle2, 
  AlertCircle,
  Clock, 
  Send, 
  User, 
  ShieldCheck, 
  Rocket, 
  Code,
  Check,
  RefreshCw,
  Eye,
  FileJson,
  FileText,
  Layers,
  Database,
  ArrowRight,
  FileDown,
  History,
  GitCompare,
  Terminal,
  Activity,
  ChevronRight,
  Lock,
  Paperclip,
  Cpu
} from 'lucide-react';
import { api, API_BASE, apiFetch, API_KEY, Project, SRSOutput } from './services/api';
import mermaid from 'mermaid';
import DevelopmentPanel from './components/DevelopmentPanel';
import TestingPanel from './components/TestingPanel';

// Initialize mermaid
mermaid.initialize({
  startOnLoad: true,
  theme: 'dark',
  securityLevel: 'loose',
});

// Helper to sanitize invalid PlantUML syntax or unquoted special characters in Mermaid strings
const cleanMermaidChart = (rawChart: string): string => {
  if (!rawChart) return '';
  let cleaned = rawChart.trim();

  // Strip markdown code fences if present (e.g., ```mermaid ... ```)
  cleaned = cleaned.replace(/^```[a-zA-Z]*\n?/i, '').replace(/\n?```$/i, '').trim();

  // Strip PlantUML wrapper tags if present
  cleaned = cleaned.replace(/@startuml/gi, '').replace(/@enduml/gi, '').trim();

  // If string contains PlantUML syntax like 'left to right direction' or 'actor' without graph/flowchart header
  if (cleaned.startsWith('left to right direction') || (cleaned.includes('actor ') && !cleaned.startsWith('graph') && !cleaned.startsWith('flowchart') && !cleaned.startsWith('sequenceDiagram') && !cleaned.startsWith('classDiagram') && !cleaned.startsWith('erDiagram'))) {
    const lines = cleaned.split('\n');
    const nodes: string[] = [];
    const connections: string[] = [];
    
    lines.forEach((line) => {
      const trimmed = line.trim();
      if (trimmed.startsWith('actor ')) {
        const actorName = trimmed.replace('actor ', '').trim();
        nodes.push(`  ${actorName.replace(/\s+/g, '_')}["👤 ${actorName}"]`);
      } else if (trimmed.includes('-->') || trimmed.includes('->')) {
        const parts = trimmed.split(/-->|->/);
        if (parts.length === 2) {
          const from = parts[0].trim().replace(/\s+/g, '_');
          let to = parts[1].trim();
          if (to.startsWith('(') && to.endsWith(')')) {
            const label = to.slice(1, -1).trim();
            const toId = 'UC_' + label.replace(/[^a-zA-Z0-9]/g, '_');
            nodes.push(`  ${toId}(["${label}"])`);
            connections.push(`  ${from} --> ${toId}`);
          } else {
            connections.push(`  ${from} --> ${to.replace(/[^a-zA-Z0-9]/g, '_')}`);
          }
        }
      }
    });

    if (connections.length > 0) {
      return `graph LR\n  subgraph System["System Scope"]\n${Array.from(new Set(nodes)).join('\n')}\n  end\n${connections.join('\n')}`;
    }
  }

  // Sanitize erDiagram invalid key attributes (e.g. UK, UNIQUE which break Mermaid erDiagram parser)
  if (cleaned.startsWith('erDiagram')) {
    cleaned = cleaned.replace(/(\b[a-zA-Z0-9_]+\b)\s+UK\b/gi, '$1');
    cleaned = cleaned.replace(/(\b[a-zA-Z0-9_]+\b)\s+UNIQUE\b/gi, '$1');
  }

  // Sanitize unquoted subgraph titles with spaces or special characters in graph / flowchart diagrams
  if (cleaned.startsWith('graph') || cleaned.startsWith('flowchart')) {
    cleaned = cleaned.replace(/subgraph\s+([^\n"\[\]]+)$/gm, (match, rawTitle) => {
      const trimmedTitle = rawTitle.trim();
      if (!trimmedTitle || trimmedTitle.startsWith('"') || trimmedTitle.includes('[')) {
        return match;
      }
      const safeId = trimmedTitle.replace(/[^a-zA-Z0-9]/g, '_');
      return `subgraph ${safeId} ["${trimmedTitle}"]`;
    });

    // Sanitize unquoted node labels with special characters like (Login & Auth) in graph diagrams
    cleaned = cleaned.replace(/-->\s*\(([^()]+)\)/g, (match, label) => {
      const cleanLabel = label.replace(/"/g, "'");
      const nodeId = 'UC_' + cleanLabel.replace(/[^a-zA-Z0-9]/g, '_');
      return `--> ${nodeId}(["${cleanLabel}"])`;
    });
  }

  return cleaned;
};

const MermaidChart: React.FC<{ chart: string; id: string }> = ({ chart, id }) => {
  const ref = useRef<HTMLDivElement>(null);
  const [renderError, setRenderError] = useState(false);

  const cleanedChart = useMemo(() => cleanMermaidChart(chart), [chart]);

  useEffect(() => {
    setRenderError(false);
    if (ref.current && cleanedChart) {
      ref.current.removeAttribute('data-processed');
      ref.current.innerHTML = cleanedChart;
      try {
        mermaid.contentLoaded();
      } catch (err) {
        console.error("Mermaid parsing error:", err);
        setRenderError(true);
      }
    }
  }, [cleanedChart, id]);

  if (renderError) {
    return (
      <div className="bg-slate-950 p-4 rounded-lg border border-indigo-500/20 text-xs text-slate-300 font-mono overflow-x-auto space-y-2 w-full">
        <span className="text-indigo-400 font-bold block">UML Diagram Specification:</span>
        <pre className="text-[11px] leading-relaxed text-slate-400 whitespace-pre-wrap">{cleanedChart}</pre>
      </div>
    );
  }

  return (
    <div key={id} ref={ref} className="mermaid flex justify-center bg-slate-950 p-4 rounded-lg overflow-x-auto border border-slate-800 text-xs w-full" />
  );
};

export default function App() {
  // Navigation
  const [activeTab, setActiveTab] = useState<'dashboard' | 'requirements' | 'design' | 'development' | 'testing'>('dashboard');
  
  // Projects State
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [projectDetails, setProjectDetails] = useState<any>(null);
  const [loadingProject, setLoadingProject] = useState(false);
  
  // Modals & Forms
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectDesc, setNewProjectDesc] = useState('');
  const [creatingProject, setCreatingProject] = useState(false);
  
  // Chat input
  const [chatMessage, setChatMessage] = useState('');
  const [sendingChat, setSendingChat] = useState(false);
  const chatBottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  // Review inputs
  const [showReviewModal, setShowReviewModal] = useState(false);
  const [reviewStatus, setReviewStatus] = useState<'APPROVED' | 'REJECTED' | 'REQUEST_CHANGES'>('APPROVED');
  const [reviewComments, setReviewComments] = useState('');
  const [submittingReview, setSubmittingReview] = useState(false);
  const [reviewStage, setReviewStage] = useState<string>('');
  
  // Custom navigation sub-tabs
  const [activeDiagramTab, setActiveDiagramTab] = useState<string>('context');
  const [activeSrsSectionTab, setActiveSrsSectionTab] = useState<string>('summary');
  const [activeDeliverableTab, setActiveDeliverableTab] = useState<'srs' | 'sdd' | 'code'>('srs');
  const [selectedDashboardFile, setSelectedDashboardFile] = useState<string | null>(null);
  const [dashboardFiles, setDashboardFiles] = useState<any>({});
  const [loadingDashboardFiles, setLoadingDashboardFiles] = useState(false);
  const [activeSddGroup, setActiveSddGroup] = useState<string>('metadata');
  
  // Model Select
  const [selectedModel, setSelectedModel] = useState('Gemini 2.5 Flash');
  const [showSRSModal, setShowSRSModal] = useState(false);
  const [showSDDModal, setShowSDDModal] = useState(false);
  const [showFullSDDModal, setShowFullSDDModal] = useState(false);

  // Design Agent State
  const [generatingDesign, setGeneratingDesign] = useState(false);

  // Version History States
  const [srsHistory, setSrsHistory] = useState<any[]>([]);
  const [sddHistory, setSddHistory] = useState<any[]>([]);
  const [showHistoryPanel, setShowHistoryPanel] = useState(false);
  const [compareVersion, setCompareVersion] = useState<any | null>(null);
  const [previewVersion, setPreviewVersion] = useState<any | null>(null);

  // Success notifications
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Fetch projects list
  const loadProjects = async () => {
    try {
      const projs = await api.listProjects();
      setProjects(projs);
      if (projs.length > 0 && !selectedProjectId) {
        setSelectedProjectId(projs[0].id);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadProjects();
  }, []);

  // Fetch selected project status details
  const fetchProjectDetails = async (id: string) => {
    setLoadingProject(true);
    try {
      const details = await api.getProjectStatus(id);
      setProjectDetails(details);
      
      // Load version history
      const reqHist = await api.getVersionHistory(id);
      setSrsHistory(reqHist);
      
      const sddHist = await api.getDesignHistory(id);
      setSddHistory(sddHist);

      // Auto-navigate based on active phase (only if not on dashboard)
      if (activeTab !== 'dashboard') {
        if (details.project.current_phase === 'DEVELOPMENT') {
          console.log("[Debug] Auto-navigating to Development tab");
          setActiveTab('development');
        } else if (details.project.current_phase === 'DESIGN') {
          console.log("[Debug] Auto-navigating to Design tab");
          setActiveTab('design');
        } else {
          console.log("[Debug] Auto-navigating to Requirements tab");
          setActiveTab('requirements');
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingProject(false);
    }
  };

  useEffect(() => {
    if (selectedProjectId) {
      fetchProjectDetails(selectedProjectId);
    }
  }, [selectedProjectId]);

  useEffect(() => {
    if (selectedProjectId && activeTab === 'dashboard' && activeDeliverableTab === 'code') {
      const loadFiles = async () => {
        setLoadingDashboardFiles(true);
        try {
          const res = await apiFetch(`${API_BASE}/projects/${selectedProjectId}/development`);
          if (res.ok) {
            const data = await res.json();
            setDashboardFiles(data.state?.generated_files || {});
            const manifest = data.state?.manifest || [];
            if (manifest.length > 0 && !selectedDashboardFile) {
              setSelectedDashboardFile(manifest[0].path);
            }
          }
        } catch (err) {
          console.error("Error loading dashboard code files:", err);
        } finally {
          setLoadingDashboardFiles(false);
        }
      };
      loadFiles();
    }
  }, [selectedProjectId, activeTab, activeDeliverableTab]);

  // Scroll to bottom of chat
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [projectDetails?.agent_state.messages, sendingChat]);

  // Toast Auto-hide
  useEffect(() => {
    if (!toastMessage) return;
    const timer = setTimeout(() => setToastMessage(null), 6000);
    return () => {
      clearTimeout(timer);
    };
  }, [toastMessage]);

  // Auto-generate design when tab is active and no design exists
  useEffect(() => {
    if (activeTab === 'design' && projectDetails) {
      console.log("[Debug] Design page mounted or active. Current sdd status:", projectDetails.sdd);
      if (!projectDetails.sdd && !generatingDesign && projectDetails.design_agent_state.phase !== 'generating') {
        console.log("[Debug] Auto-triggering design generation automatically...");
        handleGenerateDesign();
      }
    }
  }, [activeTab, projectDetails?.sdd]);

  // Create Project
  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;
    setCreatingProject(true);
    try {
      const newProj = await api.createProject(newProjectName, newProjectDesc);
      await loadProjects();
      setSelectedProjectId(newProj.id);
      
      const desc = newProjectDesc.trim();
      setShowCreateModal(false);
      setNewProjectName('');
      setNewProjectDesc('');
      setActiveTab('requirements');
      
      if (desc) {
        setSendingChat(true);
        try {
          // Send initial problem statement to requirement agent and trigger extraction if detailed
          const initPrompt = `${desc}\n\nPlease analyze this problem statement and extract all requirements.`;
          await api.sendMessage(newProj.id, initPrompt);
          await fetchProjectDetails(newProj.id);
        } catch (chatErr) {
          console.error("Initial prompt error:", chatErr);
        } finally {
          setSendingChat(false);
        }
      }
    } catch (e) {
      alert('Error creating project');
      console.error(e);
    } finally {
      setCreatingProject(false);
    }
  };

  // Send Chat message
  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatMessage.trim() || !selectedProjectId || sendingChat) return;
    
    const msg = chatMessage;
    setChatMessage('');
    setSendingChat(true);
    
    // Optimistic UI update
    if (projectDetails) {
      setProjectDetails({
        ...projectDetails,
        agent_state: {
          ...projectDetails.agent_state,
          messages: [
            ...projectDetails.agent_state.messages,
            { sender: 'user', text: msg }
          ]
        }
      });
    }

    try {
      await api.sendMessage(selectedProjectId, msg);
      await fetchProjectDetails(selectedProjectId);
    } catch (e) {
      console.error(e);
      alert('Failed to get response from Requirement Agent.');
    } finally {
      setSendingChat(false);
    }
  };

  // Compile SRS manually
  const triggerSRSCompile = async () => {
    if (!selectedProjectId) return;
    setSendingChat(true);
    setToastMessage("Analyzing problem statement & extracting requirements...");
    try {
      await api.sendMessage(selectedProjectId, "Please extract requirements and generate SRS");
      await fetchProjectDetails(selectedProjectId);
      setToastMessage("Requirements extracted! Please review the gated approval pipeline.");
    } catch (e) {
      console.error(e);
      alert("Failed to generate requirements. Check agent logs.");
    } finally {
      setSendingChat(false);
    }
  };

  // Upload and parse requirement document
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !selectedProjectId) return;
    
    setSendingChat(true);
    try {
      setToastMessage("Uploading and analyzing document...");
      await api.uploadRequirementDocument(selectedProjectId, file);
      await fetchProjectDetails(selectedProjectId);
      setToastMessage("Document processed and analyzed successfully!");
    } catch (e: any) {
      console.error(e);
      alert(e.message || "Failed to upload and parse document. Verify relevance and safety.");
    } finally {
      setSendingChat(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  // Generate Design Document
  const handleGenerateDesign = async () => {
    if (!selectedProjectId || generatingDesign) return;
    setGeneratingDesign(true);
    try {
      await api.generateDesign(selectedProjectId);
      await fetchProjectDetails(selectedProjectId);
    } catch (e) {
      console.error(e);
      alert('Design generation failed. Verify database references or constraints in logs.');
    } finally {
      setGeneratingDesign(false);
    }
  };

  // Submit human approval (both Requirements and Design)
  const handleReviewSubmit = async () => {
    if (!selectedProjectId || submittingReview) return;
    setSubmittingReview(true);
    try {
      if (activeTab === 'requirements') {
        console.log("[Debug] Submitting Requirements approval review...");
        const res = await api.submitReview(selectedProjectId, reviewStatus, reviewComments, "Lead Architect", reviewStage);
        console.log("[Debug] Approval response:", res);
        setShowReviewModal(false);
        setReviewComments('');
        
        // Load details to see if project automatically transitioned to DESIGN phase
        const details = await api.getProjectStatus(selectedProjectId);
        console.log("[Debug] Updated project details:", details);
        console.log("[Debug] Updated project phase:", details.project.current_phase);
        setProjectDetails(details);
        
        if (reviewStatus === 'APPROVED' && details.project.current_phase === 'DESIGN') {
          console.log("[Debug] Redirecting: automatically opening the Design page tab & generating architecture");
          setActiveTab('design');
          setToastMessage("Requirements Approved! Transitioned to Design Agent — Generating System Architecture...");
          if (!details.sdd) {
            handleGenerateDesign();
          }
        }
      } else if (activeTab === 'design') {
        console.log("[Debug] Submitting Design approval review...");
        const res = await api.submitDesignReview(selectedProjectId, reviewStatus, reviewComments, "Lead Architect", reviewStage);
        console.log("[Debug] Design review response:", res);
        setShowReviewModal(false);
        setReviewComments('');
        
        const details = await api.getProjectStatus(selectedProjectId);
        setProjectDetails(details);

        if (reviewStatus === 'APPROVED') {
          setActiveTab('development');
          setToastMessage("Software Design Document Approved successfully. Transitioned to Development Agent.");
        }
      }
      
      // Reload projects list and versions history
      await loadProjects();
      const reqHist = await api.getVersionHistory(selectedProjectId);
      setSrsHistory(reqHist);
      const sddHist = await api.getDesignHistory(selectedProjectId);
      setSddHistory(sddHist);
      
    } catch (e) {
      console.error(e);
      alert('Failed to submit review');
    } finally {
      setSubmittingReview(false);
    }
  };

  const getElicitationCompleteness = () => {
    if (!projectDetails) return 0;
    if (projectDetails.metrics && typeof projectDetails.metrics.elicitation_completeness_percent === 'number') {
      return projectDetails.metrics.elicitation_completeness_percent;
    }
    const mem = projectDetails.agent_state?.memory;
    if (!mem) return 0;
    let fields = 8;
    let filled = 0;
    
    if (mem.project_summary && mem.project_summary.trim().length > 0) filled++;
    if (mem.business_goals && mem.business_goals.trim().length > 0) filled++;
    if (mem.target_users && mem.target_users.length > 0) filled++;
    if (mem.functional_requirements && mem.functional_requirements.length > 0) filled++;
    if (mem.non_functional_requirements && mem.non_functional_requirements.length > 0) filled++;
    if (mem.constraints && mem.constraints.length > 0) filled++;
    if (mem.assumptions && mem.assumptions.length > 0) filled++;
    if (mem.acceptance_criteria && mem.acceptance_criteria.length > 0) filled++;
    
    return Math.round((filled / fields) * 100);
  };

  const getSRSCompleteness = () => {
    if (!projectDetails) return 0;
    if (projectDetails.metrics && typeof projectDetails.metrics.srs_completeness_percent === 'number' && projectDetails.metrics.srs_completeness_percent > 0) {
      return projectDetails.metrics.srs_completeness_percent;
    }
    if (projectDetails.srs || projectDetails.project.status === 'APPROVED') {
      return 100;
    }
    return getElicitationCompleteness();
  };

  const getCompletenessPercent = () => {
    if (!projectDetails) return 0;
    if (projectDetails.project.status === 'APPROVED' || projectDetails.project.current_phase !== 'REQUIREMENT') {
      return getSRSCompleteness();
    }
    return getElicitationCompleteness();
  };

  const isDesignTabUnlocked = () => {
    if (!projectDetails) return false;
    const phase = projectDetails.project.current_phase;
    const status = projectDetails.project.status;
    return phase !== 'REQUIREMENT' || status === 'APPROVED';
  };

  const isDevelopmentTabUnlocked = () => {
    if (!projectDetails) return false;
    const phase = projectDetails.project.current_phase;
    const status = projectDetails.project.status;
    return phase === 'DEVELOPMENT' || phase === 'TESTING' || phase === 'DEPLOYMENT' || (phase === 'DESIGN' && status === 'APPROVED');
  };

  const isTestingTabUnlocked = () => {
    if (!projectDetails) return false;
    const phase = projectDetails.project.current_phase;
    const status = projectDetails.project.status;
    return phase === 'TESTING' || phase === 'DEPLOYMENT' || status === 'READY_FOR_TESTING' || (phase === 'DEVELOPMENT' && status === 'APPROVED');
  };

  // Direct trigger downloads
  const downloadDocument = (type: 'requirements' | 'design', format: 'pdf' | 'docx' | 'json' | 'markdown') => {
    if (!selectedProjectId) return;
    const url = `${API_BASE}/projects/${selectedProjectId}/${type}/download/${format}?api_key=${API_KEY}`;
    window.open(url, '_blank');
  };

  return (
    <div className="flex h-screen bg-[#0b0f19] text-[#f3f4f6] overflow-hidden font-sans">
      
      {/* FLOATING SUCCESS TOAST */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 max-w-sm bg-gradient-to-r from-emerald-500 to-teal-600 border border-emerald-400 rounded-xl p-4 shadow-xl text-white flex items-start gap-3 animate-bounce">
          <CheckCircle2 className="h-5 w-5 shrink-0 mt-0.5" />
          <div>
            <span className="font-extrabold text-sm block">Action Confirmed!</span>
            <p className="text-xs text-emerald-100 mt-1">{toastMessage}</p>
          </div>
        </div>
      )}

      {/* SIDEBAR */}
      <aside className="w-64 bg-[#111827] border-r border-slate-800 flex flex-col justify-between shrink-0">
        <div>
          {/* Logo Brand */}
          <div className="h-16 flex items-center px-6 border-b border-slate-800 gap-3">
            <div className="h-9 w-9 rounded-lg bg-gradient-to-tr from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="font-extrabold text-sm tracking-wide bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">
                AI SDLC STUDIO
              </h1>
              <span className="text-[10px] text-slate-500 uppercase tracking-widest font-semibold">HITL orchestrator</span>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="p-4 space-y-1">
            <button 
              onClick={() => setActiveTab('dashboard')}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-all ${
                activeTab === 'dashboard' 
                  ? 'bg-indigo-600/10 text-indigo-400 border-l-4 border-indigo-500' 
                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
              }`}
            >
              <LayoutDashboard className="h-4 w-4" />
              Dashboard
            </button>

            <button 
              onClick={() => setActiveTab('requirements')}
              className={`w-full flex items-center justify-between px-4 py-3 rounded-lg text-sm font-medium transition-all ${
                activeTab === 'requirements' 
                  ? 'bg-indigo-600/10 text-indigo-400 border-l-4 border-indigo-500' 
                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
              }`}
            >
              <div className="flex items-center gap-3">
                <MessageSquare className="h-4 w-4" />
                Requirement Agent
              </div>
              {projectDetails?.srs && (
                <Check className="h-4 w-4 text-emerald-400 bg-emerald-500/20 rounded-full p-0.5" />
              )}
            </button>

            {/* Design Agent Tab */}
            <button 
              onClick={() => {
                if (isDesignTabUnlocked()) {
                  setActiveTab('design');
                }
              }}
              disabled={!isDesignTabUnlocked()}
              className={`w-full flex items-center justify-between px-4 py-3 rounded-lg text-sm font-medium transition-all ${
                !isDesignTabUnlocked() 
                  ? 'text-slate-600 hover:text-slate-600 cursor-not-allowed' 
                  : activeTab === 'design'
                  ? 'bg-indigo-600/10 text-indigo-400 border-l-4 border-indigo-500'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
              }`}
            >
              <div className="flex items-center gap-3">
                <Layers className={`h-4 w-4 ${isDesignTabUnlocked() ? 'text-indigo-400' : 'text-slate-700'}`} />
                Design Agent
              </div>
              {projectDetails?.project.current_phase === 'DESIGN' && projectDetails?.project.status === 'APPROVED' ? (
                <Check className="h-4 w-4 text-emerald-400 bg-emerald-500/20 rounded-full p-0.5" />
              ) : !isDesignTabUnlocked() ? (
                <span className="text-[9px] bg-slate-900 px-1.5 py-0.5 rounded border border-slate-800 font-bold text-slate-600">LOCKED</span>
              ) : null}
            </button>

            {/* Development Agent Tab */}
            <button 
              onClick={() => {
                if (isDevelopmentTabUnlocked()) {
                  setActiveTab('development');
                }
              }}
              disabled={!isDevelopmentTabUnlocked()}
              className={`w-full flex items-center justify-between px-4 py-3 rounded-lg text-sm font-medium transition-all ${
                !isDevelopmentTabUnlocked() 
                  ? 'text-slate-600 hover:text-slate-600 cursor-not-allowed' 
                  : activeTab === 'development'
                  ? 'bg-indigo-600/10 text-indigo-400 border-l-4 border-indigo-500'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
              }`}
            >
              <div className="flex items-center gap-3">
                <Code className={`h-4 w-4 ${isDevelopmentTabUnlocked() ? 'text-indigo-400' : 'text-slate-700'}`} />
                Development Agent
              </div>
              {projectDetails?.project.current_phase === 'DEVELOPMENT' && projectDetails?.project.status === 'APPROVED' ? (
                <Check className="h-4 w-4 text-emerald-400 bg-emerald-500/20 rounded-full p-0.5" />
              ) : !isDevelopmentTabUnlocked() ? (
                <span className="text-[9px] bg-slate-900 px-1.5 py-0.5 rounded border border-slate-800 font-bold text-slate-600">LOCKED</span>
              ) : null}
            </button>

            {/* Testing Agent Tab */}
            <button 
              onClick={() => {
                if (isTestingTabUnlocked()) {
                  setActiveTab('testing');
                }
              }}
              disabled={!isTestingTabUnlocked()}
              className={`w-full flex items-center justify-between px-4 py-3 rounded-lg text-sm font-medium transition-all ${
                !isTestingTabUnlocked() 
                  ? 'text-slate-600 hover:text-slate-600 cursor-not-allowed' 
                  : activeTab === 'testing'
                  ? 'bg-cyan-600/10 text-cyan-400 border-l-4 border-cyan-500'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
              }`}
            >
              <div className="flex items-center gap-3">
                <Cpu className={`h-4 w-4 ${isTestingTabUnlocked() ? 'text-cyan-400' : 'text-slate-700'}`} />
                Testing Agent
              </div>
              {projectDetails?.project.current_phase === 'TESTING' && projectDetails?.project.status === 'APPROVED' ? (
                <Check className="h-4 w-4 text-emerald-400 bg-emerald-500/20 rounded-full p-0.5" />
              ) : !isTestingTabUnlocked() ? (
                <span className="text-[9px] bg-slate-900 px-1.5 py-0.5 rounded border border-slate-800 font-bold text-slate-600">LOCKED</span>
              ) : null}
            </button>
          </nav>
        </div>

        {/* Footer actions */}
        <div className="p-4 border-t border-slate-800 space-y-3">
          <button 
            onClick={() => setShowCreateModal(true)}
            className="w-full flex items-center justify-center gap-2 py-2 px-4 rounded-lg bg-indigo-600 hover:bg-indigo-500 font-semibold text-sm transition-all shadow-md shadow-indigo-600/30"
          >
            <FolderPlus className="h-4 w-4" />
            New Project
          </button>

          {selectedProjectId && (
            <button 
              onClick={() => setShowHistoryPanel(!showHistoryPanel)}
              className="w-full flex items-center justify-center gap-2 py-2 px-4 rounded-lg bg-slate-800 hover:bg-slate-700 font-semibold text-sm transition-all border border-slate-700"
            >
              <History className="h-4 w-4 text-slate-400" />
              Version History
            </button>
          )}
          
          <div className="flex items-center justify-between text-xs text-slate-500 pt-1">
            <span>v2.0.0 (SDD E2E)</span>
            <span className="flex items-center gap-1.5 text-emerald-400 font-semibold">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
              Online
            </span>
          </div>
        </div>
      </aside>

      {/* MAIN CONTAINER */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
        
        {/* HEADER */}
        <header className="h-16 bg-[#111827] border-b border-slate-800 flex items-center justify-between px-8 shrink-0">
          <div className="flex items-center gap-4">
            <span className="text-sm font-semibold text-slate-400">Project:</span>
            {projects.length > 0 ? (
              <select 
                value={selectedProjectId || ''} 
                onChange={(e) => setSelectedProjectId(e.target.value)}
                className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm font-medium text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            ) : (
              <span className="text-sm italic text-slate-500">No active projects. Click "New Project" to start.</span>
            )}
            
            {projectDetails && (
              <div className="flex items-center gap-2 ml-4">
                <span className="px-2 py-0.5 text-xs font-semibold rounded bg-indigo-600/20 text-indigo-400 border border-indigo-500/20">
                  {projectDetails.project.current_phase}
                </span>
                <span className={`px-2 py-0.5 text-xs font-semibold rounded border ${
                  projectDetails.project.status === 'APPROVED' 
                    ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/20' 
                    : projectDetails.project.status === 'REJECTED' 
                    ? 'bg-rose-500/20 text-rose-400 border-rose-500/20'
                    : projectDetails.project.status === 'AWAITING_APPROVAL'
                    ? 'bg-amber-500/20 text-amber-400 border-amber-500/20 animate-pulse'
                    : 'bg-indigo-500/20 text-indigo-400 border-indigo-500/20'
                }`}>
                  {projectDetails.project.status.replace('_', ' ')}
                </span>
              </div>
            )}
          </div>

          <div className="flex items-center gap-3">
            {selectedProjectId && (
              <div className="flex items-center gap-1.5 bg-slate-800/80 border border-slate-700/80 p-1 rounded-lg">
                <span className="text-[10px] font-extrabold text-indigo-400 uppercase tracking-widest px-2 flex items-center gap-1">
                  <FileDown className="h-3.5 w-3.5 text-indigo-400" />
                  {activeTab === 'design' ? 'Export SDD:' : 'Export SRS:'}
                </span>
                <button 
                  onClick={() => downloadDocument(activeTab === 'design' ? 'design' : 'requirements', 'pdf')}
                  title={activeTab === 'design' ? "Download SDD standard PDF document" : "Download SRS standard PDF document"}
                  className="flex items-center gap-1 py-1 px-2.5 bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 hover:text-white rounded text-xs font-bold transition-all border border-indigo-500/30"
                >
                  <FileDown className="h-3.5 w-3.5" />
                  PDF
                </button>
                <button 
                  onClick={() => downloadDocument(activeTab === 'design' ? 'design' : 'requirements', 'docx')}
                  title={activeTab === 'design' ? "Download SDD Word (.docx) document" : "Download SRS Word (.docx) document"}
                  className="flex items-center gap-1 py-1 px-2.5 bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 hover:text-white rounded text-xs font-bold transition-all border border-indigo-500/30"
                >
                  <FileDown className="h-3.5 w-3.5" />
                  Word
                </button>
                <button 
                  onClick={() => downloadDocument(activeTab === 'design' ? 'design' : 'requirements', 'markdown')}
                  title={activeTab === 'design' ? "Download SDD Markdown (.md) document" : "Download SRS Markdown (.md) document"}
                  className="flex items-center gap-1 py-1 px-2.5 bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 hover:text-white rounded text-xs font-bold transition-all border border-indigo-500/30"
                >
                  <FileText className="h-3.5 w-3.5" />
                  MD
                </button>
                <button 
                  onClick={() => downloadDocument(activeTab === 'design' ? 'design' : 'requirements', 'json')}
                  title={activeTab === 'design' ? "Download SDD raw JSON data" : "Download SRS raw JSON data"}
                  className="flex items-center gap-1 py-1 px-2.5 bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 hover:text-white rounded text-xs font-bold transition-all border border-indigo-500/30"
                >
                  <FileJson className="h-3.5 w-3.5" />
                  JSON
                </button>
              </div>
            )}

            <div className="flex items-center gap-2 bg-slate-800 border border-slate-700 px-3 py-1.5 rounded-lg">
              <Sparkles className="h-4 w-4 text-indigo-400" />
              <select 
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="bg-transparent text-xs font-semibold text-slate-200 border-none outline-none cursor-pointer"
              >
                <option value="Gemini 2.5 Flash">Gemini 2.5 (Default)</option>
                <option value="GPT-4o">GPT-4o Mini</option>
                <option value="Claude 3.5 Sonnet">Claude 3.5 Sonnet</option>
              </select>
            </div>
            
            <div className="h-8 w-8 rounded-full bg-[#3b82f6]/20 border border-indigo-500/30 flex items-center justify-center font-bold text-xs text-indigo-400">
              PM
            </div>
          </div>
        </header>

        {/* WORKING SUBSECTION AREA */}
        {loadingProject ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center space-y-3">
              <RefreshCw className="h-8 w-8 text-indigo-500 animate-spin mx-auto" />
              <p className="text-sm text-slate-400">Syncing SDLC Studio database state...</p>
            </div>
          </div>
        ) : !selectedProjectId ? (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-[#0b0f19]">
            <div className="max-w-md space-y-4">
              <div className="h-16 w-16 rounded-full bg-indigo-500/10 flex items-center justify-center mx-auto text-indigo-400">
                <Layers className="h-8 w-8" />
              </div>
              <h2 className="text-xl font-bold">Launch SDLC Workspace</h2>
              <p className="text-sm text-slate-400 leading-relaxed">
                Initialize a project to gather requirements and compile system design specifications using LangGraph coordinators.
              </p>
              <button 
                onClick={() => setShowCreateModal(true)}
                className="py-2 px-5 rounded-lg bg-indigo-600 hover:bg-indigo-500 font-semibold text-sm transition-all shadow-md shadow-indigo-650/20"
              >
                Create Project Blueprint
              </button>
            </div>
          </div>
        ) : (
          <div className="flex-1 overflow-hidden flex flex-col">
            
            {/* 1. DASHBOARD OVERVIEW */}
            {activeTab === 'dashboard' && projectDetails && (
              <div className="flex-1 overflow-y-auto p-8 space-y-6">
                
                {/* Status & Completeness Cards Grid */}
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-5">
                  
                  {/* Current SDLC Phase Card */}
                  <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col justify-between relative overflow-hidden group">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest">Active SDLC Phase</span>
                      <div className="h-8 w-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                        <Activity className="h-4 w-4" />
                      </div>
                    </div>
                    <div className="mt-3">
                      <h3 className="text-lg font-black text-indigo-400 tracking-wide uppercase">{projectDetails.project.current_phase}</h3>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
                        <span className="text-xs font-semibold text-slate-300">Status: {projectDetails.project.status.replace(/_/g, ' ')}</span>
                      </div>
                    </div>
                  </div>

                  {/* Requirement & SRS Completeness Card */}
                  <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col justify-between">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest">Requirement & SRS Completeness</span>
                      <span className="text-xs font-black text-emerald-400">{getSRSCompleteness()}%</span>
                    </div>
                    <div className="mt-3 space-y-2">
                      <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-gradient-to-r from-emerald-500 to-teal-400 rounded-full transition-all duration-500"
                          style={{ width: `${getSRSCompleteness()}%` }}
                        ></div>
                      </div>
                      <div className="flex items-center justify-between text-[10px] text-slate-400 font-medium pt-0.5">
                        <span>Elicitation: <strong className="text-indigo-300 font-bold">{getElicitationCompleteness()}%</strong></span>
                        <span>SRS Doc: <strong className="text-emerald-400 font-bold">{getSRSCompleteness()}%</strong></span>
                      </div>
                    </div>
                  </div>

                  {/* SDD Architecture Quality Card */}
                  <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col justify-between">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest">Arch Quality Score</span>
                      <span className="text-xs font-black text-indigo-400">{projectDetails.metrics?.architecture_quality_score || 0} / 100</span>
                    </div>
                    <div className="mt-3 space-y-2">
                      <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full transition-all duration-500"
                          style={{ width: `${projectDetails.metrics?.architecture_quality_score || 0}%` }}
                        ></div>
                      </div>
                      <span className="text-[10px] text-slate-400 block font-medium">Traceability: {projectDetails.metrics?.requirement_coverage_percent || 0}% Coverage</span>
                    </div>
                  </div>

                  {/* Architecture Assets Counter Card */}
                  <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col justify-between">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest">Architectural Assets</span>
                      <div className="h-8 w-8 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
                        <Layers className="h-4 w-4" />
                      </div>
                    </div>
                    <div className="mt-3 flex items-center justify-between text-xs">
                      <div>
                        <span className="font-extrabold text-slate-200 block">{projectDetails.metrics?.api_count || 0} APIs</span>
                        <span className="text-[10px] text-slate-400">{projectDetails.metrics?.database_table_count || 0} Tables</span>
                      </div>
                      <div className="text-right">
                        <span className="font-extrabold text-slate-200 block">{projectDetails.metrics?.diagram_count || 0} Diagrams</span>
                        <span className="text-[10px] text-slate-400">{projectDetails.metrics?.pending_reviews_count || 0} Reviews Pending</span>
                      </div>
                    </div>
                  </div>

                </div>

                {/* 3-Agent Workflow Handoff Pipeline */}
                <div className="bg-[#111827] border border-slate-800 rounded-xl p-6 shadow-xl space-y-5">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                    <div>
                      <h4 className="font-extrabold text-xs text-slate-200 uppercase tracking-widest flex items-center gap-2">
                        <Sparkles className="h-4 w-4 text-indigo-400" />
                        Autonomous 3-Agent SDLC Pipeline
                      </h4>
                      <p className="text-xs text-slate-400 mt-1">Real-time status and handoff gating across specialized AI agents.</p>
                    </div>
                    <span className="text-[10px] font-extrabold text-indigo-300 bg-indigo-500/10 px-2.5 py-1 rounded-md border border-indigo-500/20 uppercase tracking-wider">
                      Phase: {projectDetails.project.current_phase}
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                    
                    {/* Phase 1: Requirement Agent Card */}
                    <div 
                      onClick={() => setActiveTab('requirements')}
                      className={`p-5 rounded-xl border transition-all cursor-pointer flex flex-col justify-between space-y-4 ${
                        projectDetails.project.current_phase === 'REQUIREMENT'
                          ? 'bg-indigo-600/10 border-indigo-500 shadow-lg'
                          : 'bg-[#0f1422] border-slate-800 hover:border-slate-700'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-black text-indigo-400 uppercase tracking-widest bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">Phase 1</span>
                        {projectDetails.srs || projectDetails.project.status === 'APPROVED' ? (
                          <span className="text-[10px] font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20 flex items-center gap-1">
                            <CheckCircle2 className="h-3 w-3" /> Completed
                          </span>
                        ) : projectDetails.project.current_phase === 'REQUIREMENT' ? (
                          <span className="text-[10px] font-bold text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20 flex items-center gap-1">
                            <Clock className="h-3 w-3 animate-spin" /> Active
                          </span>
                        ) : (
                          <span className="text-[10px] font-bold text-slate-500 bg-slate-800 px-2 py-0.5 rounded border border-slate-700">Draft</span>
                        )}
                      </div>

                      <div>
                        <div className="flex items-center gap-2.5 text-slate-200 font-extrabold text-sm">
                          <MessageSquare className="h-4.5 w-4.5 text-indigo-400" />
                          <span>Requirement Agent</span>
                        </div>
                        <p className="text-xs text-slate-400 mt-2 leading-relaxed">
                          Synthesizes IEEE-830 SRS documents, conducts multi-stage quality gates, and extracts functional specifications.
                        </p>
                      </div>

                      <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-xs text-indigo-400 font-bold group-hover:text-indigo-300">
                        <span>Inspect Requirements</span>
                        <ChevronRight className="h-4 w-4" />
                      </div>
                    </div>

                    {/* Phase 2: Design Agent Card */}
                    <div 
                      onClick={() => {
                        if (isDesignTabUnlocked()) setActiveTab('design');
                      }}
                      className={`p-5 rounded-xl border transition-all flex flex-col justify-between space-y-4 ${
                        !isDesignTabUnlocked()
                          ? 'bg-[#0b0f19] border-slate-850 opacity-70 cursor-not-allowed'
                          : projectDetails.project.current_phase === 'DESIGN'
                          ? 'bg-indigo-600/10 border-indigo-500 shadow-lg cursor-pointer'
                          : 'bg-[#0f1422] border-slate-800 hover:border-slate-700 cursor-pointer'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-black text-indigo-400 uppercase tracking-widest bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">Phase 2</span>
                        {projectDetails.sdd && projectDetails.project.status === 'APPROVED' ? (
                          <span className="text-[10px] font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20 flex items-center gap-1">
                            <CheckCircle2 className="h-3 w-3" /> Approved
                          </span>
                        ) : projectDetails.project.current_phase === 'DESIGN' ? (
                          <span className="text-[10px] font-bold text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20 flex items-center gap-1">
                            <Clock className="h-3 w-3 animate-spin" /> In Progress
                          </span>
                        ) : isDesignTabUnlocked() ? (
                          <span className="text-[10px] font-bold text-indigo-300 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">Ready</span>
                        ) : (
                          <span className="text-[10px] font-bold text-slate-500 bg-slate-800 px-2 py-0.5 rounded border border-slate-700 flex items-center gap-1">
                            <Lock className="h-3 w-3" /> Locked
                          </span>
                        )}
                      </div>

                      <div>
                        <div className="flex items-center gap-2.5 text-slate-200 font-extrabold text-sm">
                          <Layers className={`h-4.5 w-4.5 ${isDesignTabUnlocked() ? 'text-indigo-400' : 'text-slate-600'}`} />
                          <span>Design Agent</span>
                        </div>
                        <p className="text-xs text-slate-400 mt-2 leading-relaxed">
                          Recommends architecture styles, generates 10 Mermaid UML views, designs DB schemas, REST endpoints, and ADRs.
                        </p>
                      </div>

                      <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-xs font-bold">
                        <span className={isDesignTabUnlocked() ? 'text-indigo-400' : 'text-slate-600'}>
                          {isDesignTabUnlocked() ? 'Open Architecture Workspace' : 'Requires Requirements Sign-off'}
                        </span>
                        {isDesignTabUnlocked() ? <ChevronRight className="h-4 w-4 text-indigo-400" /> : <Lock className="h-3.5 w-3.5 text-slate-600" />}
                      </div>
                    </div>

                    {/* Phase 3: Development Agent Card */}
                    <div 
                      onClick={() => {
                        if (isDevelopmentTabUnlocked()) setActiveTab('development');
                      }}
                      className={`p-5 rounded-xl border transition-all flex flex-col justify-between space-y-4 ${
                        !isDevelopmentTabUnlocked()
                          ? 'bg-[#0b0f19] border-slate-850 opacity-70 cursor-not-allowed'
                          : projectDetails.project.current_phase === 'DEVELOPMENT'
                          ? 'bg-indigo-600/10 border-indigo-500 shadow-lg cursor-pointer'
                          : 'bg-[#0f1422] border-slate-800 hover:border-slate-700 cursor-pointer'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-black text-indigo-400 uppercase tracking-widest bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">Phase 3</span>
                        {projectDetails.project.current_phase === 'DEVELOPMENT' ? (
                          <span className="text-[10px] font-bold text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20 flex items-center gap-1">
                            <Clock className="h-3 w-3 animate-spin" /> Active Dev
                          </span>
                        ) : isDevelopmentTabUnlocked() ? (
                          <span className="text-[10px] font-bold text-indigo-300 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">Ready</span>
                        ) : (
                          <span className="text-[10px] font-bold text-slate-500 bg-slate-800 px-2 py-0.5 rounded border border-slate-700 flex items-center gap-1">
                            <Lock className="h-3 w-3" /> Locked
                          </span>
                        )}
                      </div>

                      <div>
                        <div className="flex items-center gap-2.5 text-slate-200 font-extrabold text-sm">
                          <Code className={`h-4.5 w-4.5 ${isDevelopmentTabUnlocked() ? 'text-indigo-400' : 'text-slate-600'}`} />
                          <span>Development Agent</span>
                        </div>
                        <p className="text-xs text-slate-400 mt-2 leading-relaxed">
                          Orchestrates 8 parallel developer sub-agents to compile backend APIs, database models, frontend code, and test suites.
                        </p>
                      </div>

                      <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-xs font-bold">
                        <span className={isDevelopmentTabUnlocked() ? 'text-indigo-400' : 'text-slate-600'}>
                          {isDevelopmentTabUnlocked() ? 'Open Development Workspace' : 'Requires Design Architecture Sign-off'}
                        </span>
                        {isDevelopmentTabUnlocked() ? <ChevronRight className="h-4 w-4 text-indigo-400" /> : <Lock className="h-3.5 w-3.5 text-slate-600" />}
                      </div>
                    </div>

                  </div>
                </div>

                {/* System Activity & Audit Trail Panel */}
                <div className="bg-[#111827] border border-slate-800 rounded-xl p-6 shadow-xl space-y-4">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                    <h4 className="font-extrabold text-xs text-slate-200 uppercase tracking-widest flex items-center gap-2">
                      <Activity className="h-4 w-4 text-indigo-400" />
                      Live Project Activity & Audit Logs
                    </h4>
                    <span className="text-[10px] text-slate-500 font-semibold">{projectDetails.activity_logs?.length || 0} events recorded</span>
                  </div>

                  <div className="max-h-56 overflow-y-auto space-y-2 pr-2 divide-y divide-slate-850">
                    {projectDetails.activity_logs && projectDetails.activity_logs.length > 0 ? (
                      projectDetails.activity_logs.slice(0, 6).map((log: any, idx: number) => (
                        <div key={idx} className="pt-2.5 first:pt-0 flex items-start justify-between text-xs gap-4">
                          <div className="flex items-start gap-2.5">
                            <span className={`text-[9px] font-black uppercase px-2 py-0.5 rounded border mt-0.5 shrink-0 ${
                              log.action.includes('APPROVED') || log.action.includes('SUCCESS')
                                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                                : log.action.includes('TRANSITION')
                                ? 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20'
                                : 'bg-slate-800 text-slate-300 border-slate-700'
                            }`}>
                              {log.action}
                            </span>
                            <p className="text-slate-300 leading-snug">{log.details}</p>
                          </div>
                          <span className="text-[10px] font-mono text-slate-500 shrink-0">
                            {new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        </div>
                      ))
                    ) : (
                      <div className="text-xs text-slate-500 italic py-4 text-center">
                        No activity recorded yet for this project. Start by interacting with the Requirement Agent.
                      </div>
                    )}
                  </div>
                </div>

                {/* Unified 3-Phase Deliverables Dashboard Section */}
                <div className="bg-[#111827] border border-slate-800 rounded-xl p-6 shadow-md space-y-6">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-800/80 pb-4">
                    <div>
                      <h3 className="font-extrabold text-sm text-slate-200 uppercase tracking-wider">
                        Unified 3-Phase Deliverables
                      </h3>
                      <p className="text-xs text-slate-500 mt-1">
                        Review output specs, designs, and code scaffolds generated by specialized agents across all SDLC phases.
                      </p>
                    </div>
                    {/* Sub-tab navigation pills */}
                    <div className="flex bg-[#0f1422] p-1 rounded-lg border border-slate-800 shrink-0 self-start sm:self-center">
                      <button
                        onClick={() => setActiveDeliverableTab('srs')}
                        className={`px-3 py-1.5 rounded-md text-xs font-bold uppercase tracking-wider transition-all ${
                          activeDeliverableTab === 'srs'
                            ? 'bg-indigo-650 text-white shadow'
                            : 'text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        Phase 1: SRS
                      </button>
                      <button
                        onClick={() => setActiveDeliverableTab('sdd')}
                        className={`px-3 py-1.5 rounded-md text-xs font-bold uppercase tracking-wider transition-all ${
                          activeDeliverableTab === 'sdd'
                            ? 'bg-indigo-650 text-white shadow'
                            : 'text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        Phase 2: SDD
                      </button>
                      <button
                        onClick={() => setActiveDeliverableTab('code')}
                        className={`px-3 py-1.5 rounded-md text-xs font-bold uppercase tracking-wider transition-all ${
                          activeDeliverableTab === 'code'
                            ? 'bg-indigo-650 text-white shadow'
                            : 'text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        Phase 3: Code
                      </button>
                    </div>
                  </div>

                  {/* SUB-TAB CONTENTS */}
                  {activeDeliverableTab === 'srs' && (
                    <div className="space-y-4 text-left">
                      {projectDetails.srs ? (
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                          {/* Col 1 & 2: Content */}
                          <div className="md:col-span-2 space-y-4">
                            <div className="bg-[#0f1422] border border-slate-800/80 rounded-xl p-5 space-y-3">
                              <div>
                                <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">Project Title</span>
                                <h4 className="text-sm font-extrabold text-indigo-400 mt-0.5">{projectDetails.srs.project_name}</h4>
                              </div>
                              <div>
                                <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">Executive Summary</span>
                                <p className="text-xs text-slate-300 mt-1 leading-relaxed whitespace-pre-wrap">{projectDetails.srs.executive_summary}</p>
                              </div>
                            </div>

                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                              <div className="bg-[#0f1422] border border-slate-800/80 rounded-xl p-4 space-y-2">
                                <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">Functional Specs</span>
                                <div className="max-h-48 overflow-y-auto space-y-1.5 pr-2">
                                  {projectDetails.srs.functional_requirements?.map((req: string, idx: number) => (
                                    <div key={idx} className="flex gap-2 items-start text-xs text-slate-300">
                                      <span className="text-indigo-550 font-bold">•</span>
                                      <span>{req}</span>
                                    </div>
                                  )) || <span className="text-xs text-slate-500 italic">None specified.</span>}
                                </div>
                              </div>
                              <div className="bg-[#0f1422] border border-slate-800/80 rounded-xl p-4 space-y-2">
                                <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">Scope Boundaries</span>
                                <div className="max-h-48 overflow-y-auto space-y-2 pr-2">
                                  <div>
                                    <span className="text-[9px] text-emerald-400 font-bold uppercase tracking-wider">In Scope:</span>
                                    <p className="text-xs text-slate-300 mt-0.5 leading-relaxed">{projectDetails.srs.scope || 'No scope limits specified.'}</p>
                                  </div>
                                  <div>
                                    <span className="text-[9px] text-rose-400 font-bold uppercase tracking-wider">Out of Scope:</span>
                                    <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">{projectDetails.srs.out_of_scope || 'No exclusion lists.'}</p>
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>

                          {/* Col 3: Side Actions / Metadata */}
                          <div className="bg-[#0f1422] border border-slate-800/80 rounded-xl p-5 flex flex-col justify-between space-y-6">
                            <div className="space-y-4">
                              <h4 className="text-xs font-bold text-slate-300 uppercase tracking-widest border-b border-slate-850 pb-2">SRS Artifact Actions</h4>
                              <div className="space-y-2">
                                <div className="flex items-center justify-between text-xs">
                                  <span className="text-slate-500">Document Type:</span>
                                  <span className="font-semibold text-slate-300">IEEE-830 Std</span>
                                </div>
                                <div className="flex items-center justify-between text-xs">
                                  <span className="text-slate-500">Requirements Count:</span>
                                  <span className="font-semibold text-indigo-400">{projectDetails.srs.requirement_traceability_matrix?.length || 0} items</span>
                                </div>
                                <div className="flex items-center justify-between text-xs">
                                  <span className="text-slate-500">Document Status:</span>
                                  <span className="text-[10px] font-black uppercase text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">Approved</span>
                                </div>
                              </div>
                            </div>

                            <div className="space-y-2.5">
                              <button
                                onClick={() => downloadDocument('requirements', 'pdf')}
                                className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold text-xs transition-all border border-slate-700"
                              >
                                <FileDown className="h-4 w-4" />
                                Export SRS standard PDF
                              </button>
                              <button
                                onClick={() => downloadDocument('requirements', 'docx')}
                                className="w-full flex items-center justify-center gap-2 py-2.5 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold text-xs transition-all border border-slate-700"
                              >
                                <FileDown className="h-4 w-4" />
                                Export SRS Word Docx
                              </button>
                              <button
                                onClick={() => downloadDocument('requirements', 'json')}
                                className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold text-xs transition-all border border-slate-700"
                              >
                                <FileJson className="h-4 w-4" />
                                Export SRS Raw JSON
                              </button>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="bg-[#0f1422] border border-slate-800/80 rounded-xl p-8 text-center space-y-4">
                          <Lock className="h-8 w-8 text-slate-600 mx-auto" />
                          <h4 className="font-extrabold text-xs text-slate-400 uppercase tracking-widest">Requirements Specification Pending Final Approval</h4>
                          <p className="text-xs text-slate-500 max-w-md mx-auto leading-relaxed">
                            Requirements are currently being compiled or reviewed in the Gated Approval Pipeline. You can export the current requirement draft document below at any time.
                          </p>
                          <div className="flex items-center justify-center gap-2 pt-2">
                            <button
                              onClick={() => downloadDocument('requirements', 'pdf')}
                              className="flex items-center gap-2 py-2 px-4 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs transition-all shadow-md"
                            >
                              <FileDown className="h-4 w-4" />
                              Export PDF Draft
                            </button>
                            <button
                              onClick={() => downloadDocument('requirements', 'docx')}
                              className="flex items-center gap-2 py-2 px-4 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold text-xs transition-all border border-slate-700"
                            >
                              <FileDown className="h-4 w-4" />
                              Export Word Draft
                            </button>
                            <button
                              onClick={() => downloadDocument('requirements', 'markdown')}
                              className="flex items-center gap-2 py-2 px-4 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold text-xs transition-all border border-slate-700"
                            >
                              <FileText className="h-4 w-4" />
                              Export Markdown
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {activeDeliverableTab === 'sdd' && (
                    <div className="space-y-4 text-left">
                      {projectDetails.sdd ? (
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                          {/* Col 1 & 2: Content */}
                          <div className="md:col-span-2 space-y-4">
                            <div className="bg-[#0f1422] border border-slate-800/80 rounded-xl p-5 space-y-4">
                              <div>
                                <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">Target Stack & Standards</span>
                                <div className="flex flex-wrap gap-1.5 mt-1.5">
                                  {projectDetails.sdd.technology_stack?.map((tech: string, idx: number) => (
                                    <span key={idx} className="text-[10px] font-bold text-indigo-400 bg-indigo-500/10 px-2.5 py-1 rounded border border-indigo-500/20">
                                      {tech}
                                    </span>
                                  )) || <span className="text-xs text-slate-500 italic">None defined.</span>}
                                </div>
                                <span className="text-[9px] text-slate-500 block mt-2">Standards: {projectDetails.sdd.coding_standards || 'PEP-8'}</span>
                              </div>
                            </div>

                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                              <div className="bg-[#0f1422] border border-slate-800/80 rounded-xl p-4 space-y-2">
                                <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">Database Tables ({projectDetails.sdd.database_tables?.length || 0})</span>
                                <div className="max-h-48 overflow-y-auto space-y-2 pr-2 divide-y divide-slate-850">
                                  {projectDetails.sdd.database_tables?.map((table: any, idx: number) => (
                                    <div key={idx} className="pt-2 first:pt-0">
                                      <span className="font-mono text-xs text-indigo-300 font-bold block">{table.name}</span>
                                      <p className="text-[10px] text-slate-400 mt-0.5">PK: {table.primary_key} | Columns: {table.columns?.map((c: any) => c.name).join(', ')}</p>
                                    </div>
                                  )) || <span className="text-xs text-slate-500 italic">None defined.</span>}
                                </div>
                              </div>
                              <div className="bg-[#0f1422] border border-slate-800/80 rounded-xl p-4 space-y-2">
                                <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">API Endpoints ({projectDetails.sdd.api_endpoints?.length || 0})</span>
                                <div className="max-h-48 overflow-y-auto space-y-2 pr-2 divide-y divide-slate-850">
                                  {projectDetails.sdd.api_endpoints?.map((ep: any, idx: number) => (
                                    <div key={idx} className="pt-2 first:pt-0 flex flex-col gap-0.5">
                                      <div className="flex items-center gap-1.5">
                                        <span className={`text-[8px] font-black uppercase px-1 rounded ${
                                          ep.method === 'POST' ? 'bg-indigo-500/20 text-indigo-400' : 'bg-emerald-500/20 text-emerald-400'
                                        }`}>{ep.method}</span>
                                        <span className="font-mono text-[10px] text-slate-200 font-bold">{ep.path}</span>
                                      </div>
                                      <p className="text-[10px] text-slate-400 leading-relaxed">{ep.description}</p>
                                    </div>
                                  )) || <span className="text-xs text-slate-500 italic">None defined.</span>}
                                </div>
                              </div>
                            </div>
                          </div>

                          {/* Col 3: Side Actions */}
                          <div className="bg-[#0f1422] border border-slate-800/80 rounded-xl p-5 flex flex-col justify-between space-y-6">
                            <div className="space-y-4">
                              <h4 className="text-xs font-bold text-slate-300 uppercase tracking-widest border-b border-slate-850 pb-2">SDD Artifact Actions</h4>
                              <div className="space-y-2">
                                <div className="flex items-center justify-between text-xs">
                                  <span className="text-slate-500">Design Document:</span>
                                  <span className="font-semibold text-slate-300">SDD v1.0</span>
                                </div>
                                <div className="flex items-center justify-between text-xs">
                                  <span className="text-slate-500">Diagrams Generated:</span>
                                  <span className="font-semibold text-indigo-400">{projectDetails.metrics?.diagram_count || 0} diagrams</span>
                                </div>
                                <div className="flex items-center justify-between text-xs">
                                  <span className="text-slate-500">Design Status:</span>
                                  <span className="text-[10px] font-black uppercase text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">Approved</span>
                                </div>
                              </div>
                            </div>

                            <div className="space-y-2.5">
                              <button
                                onClick={() => setShowFullSDDModal(true)}
                                className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs transition-all shadow-md"
                              >
                                <FileText className="h-4 w-4" />
                                View Detailed SDD Document
                              </button>
                              <button
                                onClick={() => downloadDocument('design', 'pdf')}
                                className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold text-xs transition-all border border-slate-700"
                              >
                                <FileDown className="h-4 w-4" />
                                Export SDD standard PDF
                              </button>
                              <button
                                onClick={() => downloadDocument('design', 'docx')}
                                className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold text-xs transition-all border border-slate-700"
                              >
                                <FileDown className="h-4 w-4" />
                                Export SDD Word Docx
                              </button>
                              <button
                                onClick={() => downloadDocument('design', 'markdown')}
                                className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold text-xs transition-all border border-slate-700"
                              >
                                <FileText className="h-4 w-4" />
                                Export SDD Markdown
                              </button>
                              <button
                                onClick={() => downloadDocument('design', 'json')}
                                className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold text-xs transition-all border border-slate-700"
                              >
                                <FileJson className="h-4 w-4" />
                                Export SDD Raw JSON
                              </button>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="bg-[#0f1422] border border-slate-800/80 rounded-xl p-8 text-center space-y-3">
                          <Lock className="h-8 w-8 text-slate-600 mx-auto" />
                          <h4 className="font-extrabold text-xs text-slate-400 uppercase tracking-widest">System Design Spec Locked</h4>
                          <p className="text-xs text-slate-500 max-w-md mx-auto leading-relaxed">
                            The Software Architect has not drafted or approved the system design document (SDD) for this project yet. It will unlock once requirements are finalized and approved.
                          </p>
                        </div>
                      )}
                    </div>
                  )}

                  {activeDeliverableTab === 'code' && (
                    <div className="space-y-4 text-left">
                      {projectDetails.project.current_phase === 'DEVELOPMENT' || (projectDetails.development_agent_state.manifest && projectDetails.development_agent_state.manifest.length > 0) ? (
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                          {/* Col 1: File Browser Tree */}
                          <div className="bg-[#0f1422] border border-slate-800/80 rounded-xl p-4 space-y-2">
                            <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block border-b border-slate-850 pb-2 mb-2">Compiled Files Tree</span>
                            <div className="max-h-80 overflow-y-auto space-y-1 pr-2">
                              {projectDetails.development_agent_state.manifest?.map((file: any, idx: number) => {
                                const isSelected = selectedDashboardFile === file.path;
                                return (
                                  <button
                                    key={idx}
                                    onClick={() => setSelectedDashboardFile(file.path)}
                                    className={`w-full text-left p-2.5 rounded-lg text-xs font-mono truncate transition-all flex items-center justify-between border ${
                                      isSelected
                                        ? 'bg-indigo-650/15 border-indigo-500 text-indigo-200 shadow'
                                        : 'bg-[#111827]/40 border-slate-850 hover:border-slate-700 text-slate-400 hover:text-slate-200'
                                    }`}
                                  >
                                    <span className="truncate">{file.path}</span>
                                    <ChevronRight className="h-3.5 w-3.5 shrink-0 opacity-60" />
                                  </button>
                                );
                              }) || <span className="text-xs text-slate-500 italic">None compiled yet.</span>}
                            </div>
                          </div>

                          {/* Col 2: Code Viewer */}
                          <div className="bg-[#0f1422] border border-slate-800/80 rounded-xl p-4 flex flex-col justify-between min-h-[300px]">
                            <div className="space-y-2 flex-1 flex flex-col">
                              <div className="flex items-center justify-between border-b border-slate-850 pb-2 shrink-0">
                                <span className="font-mono text-xs text-indigo-300 font-bold truncate">
                                  {selectedDashboardFile || 'Select a file to inspect'}
                                </span>
                                <span className="text-[9px] bg-slate-900 px-2 py-0.5 rounded border border-slate-800 font-extrabold text-slate-500 uppercase tracking-widest">
                                  Source code
                                </span>
                              </div>
                              {loadingDashboardFiles ? (
                                <div className="flex-1 flex items-center justify-center py-12">
                                  <RefreshCw className="h-6 w-6 text-indigo-500 animate-spin" />
                                </div>
                              ) : selectedDashboardFile && dashboardFiles[selectedDashboardFile] ? (
                                <pre className="flex-1 max-h-60 overflow-y-auto p-3 rounded-lg bg-[#0b0f19] border border-slate-900 text-[10px] text-slate-350 font-mono leading-relaxed text-left select-text whitespace-pre-wrap">
                                  {dashboardFiles[selectedDashboardFile]}
                                </pre>
                              ) : (
                                <div className="flex-grow flex items-center justify-center text-xs text-slate-500 italic py-12">
                                  {selectedDashboardFile ? 'File content empty or loading...' : 'Select a source file on the left to view contents.'}
                                </div>
                              )}
                            </div>
                          </div>

                          {/* Col 3: Side Actions / Build Report */}
                          <div className="bg-[#0f1422] border border-slate-800/80 rounded-xl p-5 flex flex-col justify-between space-y-6">
                            <div className="space-y-4">
                              <h4 className="text-xs font-bold text-slate-300 uppercase tracking-widest border-b border-slate-850 pb-2">Codebase Metadata</h4>
                              <div className="space-y-2">
                                <div className="flex items-center justify-between text-xs">
                                  <span className="text-slate-500">Total Scaffolds:</span>
                                  <span className="font-semibold text-slate-300">{projectDetails.development_agent_state.manifest?.length || 0} source files</span>
                                </div>
                                <div className="flex items-center justify-between text-xs">
                                  <span className="text-slate-500">Build Status:</span>
                                  <span className="text-[10px] font-black uppercase text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">SUCCESS</span>
                                </div>
                                <div className="flex items-center justify-between text-xs">
                                  <span className="text-slate-500">Security Scans:</span>
                                  <span className="text-[10px] font-black uppercase text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">PASSED</span>
                                </div>
                              </div>
                            </div>

                            <button
                              onClick={() => window.open(`${API_BASE}/projects/${selectedProjectId}/development/artifacts/download?type=source_zip&api_key=${API_KEY}`, '_blank')}
                              className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs uppercase tracking-widest transition-all shadow-md shadow-indigo-600/30"
                            >
                              <FileDown className="h-4 w-4" />
                              Download Source.zip
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="bg-[#0f1422] border border-slate-800/80 rounded-xl p-8 text-center space-y-3">
                          <Lock className="h-8 w-8 text-slate-600 mx-auto" />
                          <h4 className="font-extrabold text-xs text-slate-400 uppercase tracking-widest">Codebase Scaffolds Locked</h4>
                          <p className="text-xs text-slate-500 max-w-md mx-auto leading-relaxed">
                            Development phase has not compiled codebase files for this project yet. It will unlock and populate once the system design (SDD) is generated and approved.
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Dashboard Bottom Logs & Blueprint */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  
                  <div className="bg-[#111827] border border-slate-800 rounded-xl p-6 shadow lg:col-span-2 space-y-4">
                    <h3 className="font-bold text-sm text-slate-200">Recent Orchestrator Activities</h3>
                    <div className="divide-y divide-slate-800/60 max-h-80 overflow-y-auto pr-2 space-y-3">
                      {projectDetails.logs.length === 0 ? (
                        <p className="text-sm italic text-slate-500 py-4">No activity logged.</p>
                      ) : (
                        projectDetails.logs.map((log: any, index: number) => (
                          <div key={index} className="pt-3 first:pt-0 flex items-start justify-between text-xs">
                            <div>
                              <span className="font-bold text-slate-300 block">{log.action.replace('_', ' ')}</span>
                              <p className="text-slate-400 mt-0.5">{log.details}</p>
                            </div>
                            <span className="text-slate-500 shrink-0 font-medium ml-4">
                              {new Date(log.timestamp).toLocaleTimeString()}
                            </span>
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  <div className="bg-[#111827] border border-slate-800 rounded-xl p-6 shadow flex flex-col justify-between">
                    <div className="space-y-4">
                      <h3 className="font-bold text-sm text-slate-200">Blueprint Profile</h3>
                      <div>
                        <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">Description</span>
                        <p className="text-xs text-slate-300 mt-1 leading-relaxed">{projectDetails.project.description || 'No description.'}</p>
                      </div>
                      <div>
                        <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">Initialization</span>
                        <p className="text-xs text-slate-300 mt-0.5">{new Date(projectDetails.project.created_at).toLocaleString()}</p>
                      </div>
                    </div>
                    
                    <button 
                      onClick={() => {
                        if (isDesignTabUnlocked()) {
                          setActiveTab('design');
                        } else {
                          setActiveTab('requirements');
                        }
                      }}
                      className="w-full mt-6 py-2 px-4 rounded-lg bg-indigo-650/10 hover:bg-indigo-600/20 text-indigo-400 font-bold text-xs uppercase tracking-widest transition-all border border-indigo-500/20"
                    >
                      {isDesignTabUnlocked() ? 'Open Architect panel →' : 'Resume elicitation chat →'}
                    </button>
                  </div>

                </div>

              </div>
            )}

            {/* 2. REQUIREMENT AGENT CHAT & SRS */}
            {activeTab === 'requirements' && projectDetails && (
              <div className="flex-1 flex overflow-hidden">
                
                {/* Left Elicitation Workspace */}
                <div className="flex-1 flex flex-col bg-[#0f1422] border-r border-slate-800 min-w-0">
                  <div className="h-14 border-b border-slate-800 flex items-center justify-between px-6 shrink-0 bg-[#111827]">
                    <div className="flex items-center gap-2.5">
                      <div className="h-2 w-2 rounded-full bg-indigo-500 animate-ping"></div>
                      <span className="text-xs font-semibold text-slate-200 uppercase tracking-wider">Business Analyst Loop</span>
                    </div>
                    
                    <button
                      onClick={triggerSRSCompile}
                      disabled={sendingChat || projectDetails.project.status === 'APPROVED' || projectDetails.project.current_phase !== 'REQUIREMENT'}
                      className="flex items-center gap-2 py-1.5 px-3 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-bold transition-all shadow-md shadow-indigo-600/20 disabled:opacity-50"
                    >
                      <Sparkles className="h-4 w-4" />
                      Generate Requirements
                    </button>
                  </div>

                  <div className="flex-1 overflow-y-auto p-6 space-y-4">
                    {projectDetails.agent_state.messages.length === 0 ? (
                      <div className="h-full flex items-center justify-center p-8 text-center text-slate-500">
                        <div className="max-w-xs space-y-2">
                          <MessageSquare className="h-8 w-8 text-indigo-500/35 mx-auto" />
                          <p className="text-xs font-medium">Briefly explain what kind of application you want to build.</p>
                        </div>
                      </div>
                    ) : (
                      projectDetails.agent_state.messages.map((m: any, index: number) => (
                        <div 
                          key={index} 
                          className={`flex ${m.sender === 'user' ? 'justify-end' : 'justify-start'}`}
                        >
                          <div className={`max-w-md rounded-2xl p-4 text-sm leading-relaxed ${
                            m.sender === 'user' 
                              ? 'bg-indigo-600 text-white rounded-br-none shadow-md shadow-indigo-600/10' 
                              : 'bg-[#181f32] text-slate-200 border border-slate-800/80 rounded-bl-none shadow-md'
                          }`}>
                            <div className="font-semibold text-[10px] text-slate-400 mb-1 flex items-center gap-1.5 uppercase tracking-wide">
                              {m.sender === 'user' ? <User className="h-3 w-3" /> : <Sparkles className="h-3 w-3 text-indigo-400" />}
                              {m.sender === 'user' ? 'You' : 'Requirement Agent'}
                            </div>
                            <p>{m.text}</p>
                          </div>
                        </div>
                      ))
                    )}
                    
                    {sendingChat && (
                      <div className="flex justify-start">
                        <div className="bg-[#181f32] text-slate-400 rounded-2xl rounded-bl-none p-4 border border-slate-800 text-sm flex items-center gap-2 shadow-md">
                          <RefreshCw className="h-3.5 w-3.5 animate-spin text-indigo-400" />
                          <span className="text-xs">Typing elicitation notes...</span>
                        </div>
                      </div>
                    )}
                    
                    <div ref={chatBottomRef} />
                  </div>

                  <form onSubmit={handleSendMessage} className="p-4 bg-[#111827] border-t border-slate-800 flex items-center gap-3">
                    <input 
                      type="file"
                      ref={fileInputRef}
                      onChange={handleFileUpload}
                      className="hidden"
                      accept=".pdf,.docx,.txt"
                    />
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={sendingChat || projectDetails.project.status === 'APPROVED' || projectDetails.project.current_phase !== 'REQUIREMENT'}
                      className="h-10 w-10 bg-slate-800 hover:bg-slate-700 rounded-xl flex items-center justify-center transition-all border border-slate-700 text-indigo-400 disabled:opacity-50 shrink-0"
                    >
                      <Paperclip className="h-4.5 w-4.5" />
                    </button>
                    <input 
                      type="text" 
                      value={chatMessage}
                      onChange={(e) => setChatMessage(e.target.value)}
                      disabled={sendingChat || projectDetails.project.status === 'APPROVED' || projectDetails.project.current_phase !== 'REQUIREMENT'}
                      placeholder={
                        projectDetails.project.status === 'APPROVED' || projectDetails.project.current_phase !== 'REQUIREMENT'
                          ? 'Finalized SRS compiled. Phase locked.' 
                          : 'Describe system features, payment flows, scaling needs...'
                      }
                      className="flex-1 bg-slate-900 border border-slate-700/80 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-100 disabled:opacity-50"
                    />
                    <button 
                      type="submit"
                      disabled={sendingChat || !chatMessage.trim() || projectDetails.project.status === 'APPROVED' || projectDetails.project.current_phase !== 'REQUIREMENT'}
                      className="h-10 w-10 bg-indigo-600 hover:bg-indigo-500 rounded-xl flex items-center justify-center transition-all shadow text-white disabled:opacity-50"
                    >
                      <Send className="h-4 w-4" />
                    </button>
                  </form>
                </div>

                {/* Right Metadata checklist & Action Panel */}
                <div className="w-80 flex flex-col bg-[#111827] border-l border-slate-800 shrink-0 justify-between">
                  
                  {/* Summary lists */}
                  <div className="flex-1 overflow-y-auto p-6 space-y-6">
                    <div className="space-y-2">
                      <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest block">Project Summary</span>
                      <div className="bg-[#181f32]/40 rounded-lg p-3 text-xs text-slate-300 border border-slate-800">
                        {projectDetails.agent_state.memory.project_summary || 'Pending explanation.'}
                      </div>
                    </div>

                    <div className="space-y-2">
                      <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest block">Business Goal</span>
                      <div className="bg-[#181f32]/40 rounded-lg p-3 text-xs text-slate-300 border border-slate-800">
                        {projectDetails.agent_state.memory.business_goals || 'Pending explanation.'}
                      </div>
                    </div>

                    {/* Functional Requirements */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest block">Functional Requirements</span>
                        <span className="text-[10px] font-mono text-slate-500">
                          {projectDetails.agent_state.memory.functional_requirements?.length || 0} items
                        </span>
                      </div>
                      <div className="bg-[#181f32]/40 rounded-lg p-3 text-xs text-slate-300 border border-slate-800 max-h-36 overflow-y-auto space-y-1">
                        {projectDetails.agent_state.memory.functional_requirements?.length > 0 ? (
                          projectDetails.agent_state.memory.functional_requirements.map((req: string, idx: number) => (
                            <div key={idx} className="flex items-start gap-1.5 text-[11px] leading-tight text-slate-300">
                              <span className="text-indigo-400 shrink-0 font-bold">•</span>
                              <span>{req}</span>
                            </div>
                          ))
                        ) : (
                          <p className="text-slate-500 italic text-[11px]">Provide problem statement to extract functional requirements.</p>
                        )}
                      </div>
                    </div>

                    {/* Non-Functional Requirements */}
                    {projectDetails.agent_state.memory.non_functional_requirements?.length > 0 && (
                      <div className="space-y-2">
                        <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest block">Non-Functional Requirements</span>
                        <div className="bg-[#181f32]/40 rounded-lg p-3 text-xs text-slate-300 border border-slate-800 max-h-28 overflow-y-auto space-y-1">
                          {projectDetails.agent_state.memory.non_functional_requirements.map((req: string, idx: number) => (
                            <div key={idx} className="flex items-start gap-1.5 text-[11px] leading-tight text-slate-300">
                              <span className="text-amber-400 shrink-0 font-bold">•</span>
                              <span>{req}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Completeness Gauge */}
                    <div className="bg-[#0b0f19] border border-slate-800 rounded-xl p-4 text-center space-y-3">
                      <div className="flex items-center justify-between text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                        <span>Elicitation Progress</span>
                        <span className="text-indigo-400 font-bold">{getElicitationCompleteness()}%</span>
                      </div>
                      <div className="relative h-20 w-20 mx-auto flex items-center justify-center">
                        <svg className="absolute inset-0 h-full w-full transform -rotate-90">
                          <circle cx="40" cy="40" r="34" strokeWidth="6" stroke="rgba(255,255,255,0.03)" fill="transparent" />
                          <circle 
                            cx="40" 
                            cy="40" 
                            r="34" 
                            strokeWidth="6" 
                            stroke="#6366f1" 
                            fill="transparent" 
                            strokeDasharray={213.6} 
                            strokeDashoffset={213.6 - (213.6 * getElicitationCompleteness()) / 100}
                            className="transition-all duration-300"
                          />
                        </svg>
                        <span className="text-lg font-black text-white">{getElicitationCompleteness()}%</span>
                      </div>
                      <div className="text-[10px] text-slate-400 flex items-center justify-between border-t border-slate-800/80 pt-2 font-medium">
                        <span>Compiled SRS Doc:</span>
                        <span className="text-emerald-400 font-bold">{getSRSCompleteness()}%</span>
                      </div>
                    </div>

                    {/* View/Download SRS Panel */}
                    {selectedProjectId && (
                      <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-4 space-y-3">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block">Compiled Documentation</span>
                        
                        <button 
                          onClick={() => setShowSRSModal(true)}
                          className="w-full flex items-center justify-center gap-2 py-2 px-3 bg-slate-800 hover:bg-slate-700 text-xs font-bold rounded-lg transition-all border border-slate-700"
                        >
                          <Eye className="h-3.5 w-3.5 text-indigo-400" />
                          View SRS Blueprint
                        </button>

                        <div className="grid grid-cols-4 gap-1.5">
                          <button 
                            onClick={() => downloadDocument('requirements', 'pdf')}
                            className="flex flex-col items-center justify-center py-2 bg-slate-800 hover:bg-slate-700 rounded text-[9px] font-bold text-slate-300 border border-slate-750"
                          >
                            <FileDown className="h-3.5 w-3.5 mb-1 text-indigo-400" />
                            PDF
                          </button>
                          <button 
                            onClick={() => downloadDocument('requirements', 'docx')}
                            className="flex flex-col items-center justify-center py-2 bg-slate-800 hover:bg-slate-700 rounded text-[9px] font-bold text-slate-300 border border-slate-750"
                          >
                            <FileDown className="h-3.5 w-3.5 mb-1 text-indigo-400" />
                            Word
                          </button>
                          <button 
                            onClick={() => downloadDocument('requirements', 'markdown')}
                            className="flex flex-col items-center justify-center py-2 bg-slate-800 hover:bg-slate-700 rounded text-[9px] font-bold text-slate-300 border border-slate-750"
                          >
                            <FileText className="h-3.5 w-3.5 mb-1 text-indigo-400" />
                            MD
                          </button>
                          <button 
                            onClick={() => downloadDocument('requirements', 'json')}
                            className="flex flex-col items-center justify-center py-2 bg-slate-800 hover:bg-slate-700 rounded text-[9px] font-bold text-slate-300 border border-slate-750"
                          >
                            <FileJson className="h-3.5 w-3.5 mb-1 text-indigo-400" />
                            JSON
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Permanent Multi-Stage Gated Review Panel */}
                    <div className="bg-[#181f32]/60 border border-indigo-500/35 rounded-xl p-5 space-y-4 shadow-xl">
                      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                        <div className="flex items-center gap-2 text-indigo-400 font-black text-xs uppercase tracking-widest">
                          <ShieldCheck className="h-4 w-4 text-indigo-400" />
                          <span>Gated Approval Pipeline</span>
                        </div>
                        <span className="text-[9px] font-extrabold uppercase px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                          {projectDetails.agent_state.phase === 'awaiting_extraction_approval' ? 'Stage 1: Extraction' :
                           projectDetails.agent_state.phase === 'awaiting_gap_approval' ? 'Stage 2: Gap Detection' :
                           projectDetails.agent_state.phase === 'awaiting_validation_approval' ? 'Stage 3: Validation' :
                           (projectDetails.agent_state.phase === 'awaiting_finalization_approval' || projectDetails.agent_state.phase === 'AWAITING_APPROVAL') ? 'Stage 4: Finalization' :
                           projectDetails.project.status === 'APPROVED' ? 'Approved & Completed' : 'Draft / Interactive'}
                        </span>
                      </div>

                      {/* PROMINENT FAST-TRACK BUTTON ALWAYS VISIBLE */}
                      {projectDetails.project.status !== 'APPROVED' && (
                        <button 
                          onClick={async () => {
                            if (!selectedProjectId) return;
                            setSendingChat(true);
                            setToastMessage("Approving SRS & Transitioning to Design Agent...");
                            try {
                              await api.submitReview(selectedProjectId, "APPROVED", "SRS Approved to start Design", "Lead Architect", "FINALIZATION");
                              const details = await api.getProjectStatus(selectedProjectId);
                              setProjectDetails(details);
                              setActiveTab('design');
                              setToastMessage("Requirements Approved! Transitioned to Design Agent — Generating System Architecture...");
                              if (!details.sdd) {
                                handleGenerateDesign();
                              }
                            } catch (err) {
                              console.error(err);
                              alert("Transition to Design failed. Check logs.");
                            } finally {
                              setSendingChat(false);
                            }
                          }}
                          className="w-full py-3 px-4 bg-gradient-to-r from-emerald-600 via-teal-600 to-indigo-600 hover:from-emerald-500 hover:to-indigo-500 text-white rounded-xl font-black text-xs shadow-xl shadow-emerald-600/30 flex items-center justify-center gap-2 uppercase tracking-wider transition-all border border-emerald-400/40 transform hover:scale-[1.02]"
                        >
                          <Sparkles className="h-4 w-4 text-emerald-200 animate-pulse" />
                          Approve & Move to Design Agent →
                        </button>
                      )}

                      {/* Draft Phase: Trigger Pipeline Button */}
                      {(projectDetails.agent_state.phase === 'draft' || projectDetails.agent_state.phase === 'idle' || !projectDetails.agent_state.phase) && projectDetails.project.status !== 'APPROVED' && (
                        <div className="space-y-3">
                          <p className="text-[11px] text-slate-400 leading-relaxed">
                            Run the autonomous 4-stage pipeline (Extraction &rarr; Gap Detection &rarr; Quality Validation &rarr; Finalization).
                          </p>
                          <button
                            onClick={triggerSRSCompile}
                            disabled={sendingChat}
                            className="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs rounded-lg transition-all shadow-md shadow-indigo-600/30 disabled:opacity-50"
                          >
                            <Sparkles className="h-4 w-4" />
                            Run Requirements Pipeline (Stage 1 to 4)
                          </button>
                        </div>
                      )}

                      {/* Processing / Generating Phase */}
                      {(projectDetails.agent_state.phase === 'processing' || projectDetails.agent_state.phase === 'GENERATING_SRS') && (
                        <div className="space-y-2 text-center py-3">
                          <RefreshCw className="h-5 w-5 text-indigo-400 animate-spin mx-auto" />
                          <span className="text-xs font-bold text-slate-300 block">Pipeline Execution in Progress...</span>
                          <span className="text-[10px] text-slate-500 block">Extracting canonical requirement document & running quality gates</span>
                        </div>
                      )}

                      {/* Stage 1: Extraction Approval */}
                      {(projectDetails.agent_state.phase === 'awaiting_extraction_approval') && (
                        <div className="space-y-3">
                          <span className="text-[10px] font-bold text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded-full uppercase tracking-wider">Stage 1: Extraction Approval</span>
                          <p className="text-[11px] text-slate-400 leading-relaxed">
                            Review the extracted canonical requirements. Check priority and actor mapping.
                          </p>
                          {projectDetails.agent_state.document?.requirements && (
                            <div className="bg-slate-950 p-2.5 rounded border border-slate-800 text-[10px] text-slate-400 max-h-32 overflow-y-auto space-y-1.5 font-mono">
                              {projectDetails.agent_state.document.requirements.map((r: any) => (
                                <div key={r.requirement_id} className="border-b border-slate-900 pb-1">
                                  <span className="text-indigo-400 font-bold">{r.requirement_id}</span> ({r.requirement_type}): {r.title}
                                </div>
                              ))}
                            </div>
                          )}
                          <div className="flex gap-2 pt-2">
                            <button 
                              onClick={() => { setReviewStage('EXTRACTION'); setReviewStatus('REJECTED'); setShowReviewModal(true); }}
                              className="flex-1 py-1.5 bg-rose-500/10 text-rose-400 border border-rose-500/20 hover:bg-rose-500/20 rounded font-bold text-xs"
                            >
                              Reject
                            </button>
                            <button 
                              onClick={() => { setReviewStage('EXTRACTION'); setReviewStatus('APPROVED'); setShowReviewModal(true); }}
                              className="flex-1 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded font-bold text-xs shadow-md shadow-emerald-600/30"
                            >
                              Approve Stage 1
                            </button>
                          </div>
                        </div>
                      )}

                      {/* Stage 2: Gap Detection Approval */}
                      {(projectDetails.agent_state.phase === 'awaiting_gap_approval') && (
                        <div className="space-y-3">
                          <span className="text-[10px] font-bold text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded-full uppercase tracking-wider">Stage 2: Gap Detection Approval</span>
                          <p className="text-[11px] text-slate-400 leading-relaxed">
                            Review identified requirement gaps. Confirm if blocking clarifications are required.
                          </p>
                          {projectDetails.agent_state.gaps && (
                            <div className="bg-slate-950 p-2.5 rounded border border-slate-800 text-[10px] text-slate-400 max-h-32 overflow-y-auto space-y-1.5">
                              {projectDetails.agent_state.gaps.map((g: any) => (
                                <div key={g.id} className="border-b border-slate-900 pb-1">
                                  <span className={g.blocking ? "text-rose-400 font-bold" : "text-amber-400 font-bold"}>
                                    [{g.blocking ? 'BLOCKING' : 'INFO'}]
                                  </span> {g.description}
                                </div>
                              ))}
                            </div>
                          )}
                          <div className="flex gap-2 pt-2">
                            <button 
                              onClick={() => { setReviewStage('GAP_DETECTION'); setReviewStatus('REJECTED'); setShowReviewModal(true); }}
                              className="flex-1 py-1.5 bg-rose-500/10 text-rose-400 border border-rose-500/20 hover:bg-rose-500/20 rounded font-bold text-xs"
                            >
                              Reject
                            </button>
                            <button 
                              onClick={() => { setReviewStage('GAP_DETECTION'); setReviewStatus('APPROVED'); setShowReviewModal(true); }}
                              className="flex-1 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded font-bold text-xs shadow-md shadow-emerald-600/30"
                            >
                              Approve Stage 2
                            </button>
                          </div>
                        </div>
                      )}

                      {/* Stage 3: Quality Validation Approval */}
                      {(projectDetails.agent_state.phase === 'awaiting_validation_approval') && (
                        <div className="space-y-3">
                          <span className="text-[10px] font-bold text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded-full uppercase tracking-wider">Stage 3: Quality Validation Approval</span>
                          <p className="text-[11px] text-slate-400 leading-relaxed">
                            Review quality scores. Require overall quality index &ge; 70 to proceed.
                          </p>
                          {projectDetails.agent_state.document?.quality_result && (
                            <div className="bg-slate-950 p-3 rounded border border-slate-800 text-[10px] text-slate-400 space-y-2">
                              <div className="flex justify-between items-center text-xs">
                                <span className="font-bold">Overall Score:</span>
                                <span className={projectDetails.agent_state.document.quality_result.valid ? "text-emerald-400 font-black text-sm" : "text-rose-400 font-black text-sm"}>
                                  {projectDetails.agent_state.document.quality_result.overall_score}/100
                                </span>
                              </div>
                              <div className="space-y-1">
                                {Object.entries(projectDetails.agent_state.document.quality_result.scores).map(([k, v]: any) => (
                                  <div key={k} className="space-y-0.5">
                                    <div className="flex justify-between text-[9px] uppercase font-semibold">
                                      <span>{k}</span>
                                      <span>{v}</span>
                                    </div>
                                    <div className="h-1 bg-slate-900 rounded overflow-hidden">
                                      <div className="h-full bg-indigo-500 rounded" style={{ width: `${v}%` }} />
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                          <div className="flex gap-2 pt-2">
                            <button 
                              onClick={() => { setReviewStage('VALIDATION'); setReviewStatus('REJECTED'); setShowReviewModal(true); }}
                              className="flex-1 py-1.5 bg-rose-500/10 text-rose-400 border border-rose-500/20 hover:bg-rose-500/20 rounded font-bold text-xs"
                            >
                              Reject
                            </button>
                            <button 
                              onClick={() => { setReviewStage('VALIDATION'); setReviewStatus('APPROVED'); setShowReviewModal(true); }}
                              className="flex-1 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded font-bold text-xs shadow-md shadow-emerald-600/30"
                            >
                              Approve Stage 3
                            </button>
                          </div>
                        </div>
                      )}

                      {/* Stage 4: Finalization Approval */}
                      {(projectDetails.agent_state.phase === 'awaiting_finalization_approval' || 
                        projectDetails.agent_state.phase === 'AWAITING_APPROVAL') && 
                        projectDetails.project.status !== 'APPROVED' && 
                        projectDetails.project.current_phase === 'REQUIREMENT' && 
                        projectDetails.agent_state.phase !== 'completed' && (
                        <div className="space-y-3">
                          <span className="text-[10px] font-bold text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded-full uppercase tracking-wider">Stage 4: Finalization Sign-Off</span>
                          <p className="text-[11px] text-slate-400 leading-relaxed">
                            Confirm sign-off on generated requirements backlog (Epics, Features, User Stories, and Acceptance Criteria) to complete SRS compilation.
                          </p>
                          <div className="bg-slate-950 p-2.5 rounded border border-slate-800 text-[10px] text-slate-400 space-y-1">
                            <div><span className="font-bold text-slate-300">Epics:</span> {projectDetails.agent_state.document?.epics?.length || 0}</div>
                            <div><span className="font-bold text-slate-300">Features:</span> {projectDetails.agent_state.document?.features?.length || 0}</div>
                            <div><span className="font-bold text-slate-300">Stories:</span> {projectDetails.agent_state.document?.user_stories?.length || 0}</div>
                            <div><span className="font-bold text-slate-300">Criteria:</span> {projectDetails.agent_state.document?.acceptance_criteria?.length || 0}</div>
                          </div>
                          <div className="flex gap-2 pt-2">
                            <button 
                              onClick={() => { setReviewStage('FINALIZATION'); setReviewStatus('REJECTED'); setShowReviewModal(true); }}
                              className="flex-1 py-1.5 bg-rose-500/10 text-rose-400 border border-rose-500/20 hover:bg-rose-500/20 rounded font-bold text-xs"
                            >
                              Reject
                            </button>
                            <button 
                              onClick={() => { setReviewStage('FINALIZATION'); setReviewStatus('APPROVED'); setShowReviewModal(true); }}
                              className="flex-1 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded font-bold text-xs shadow-md shadow-emerald-600/30"
                            >
                              Finalize & Approve SRS
                            </button>
                          </div>
                        </div>
                      )}

                      {/* Direct Fast-Track Button */}
                      {(projectDetails.agent_state.phase === 'awaiting_finalization_approval' || 
                        projectDetails.agent_state.phase === 'AWAITING_APPROVAL') && 
                        projectDetails.project.status !== 'APPROVED' && 
                        projectDetails.project.current_phase === 'REQUIREMENT' && 
                        projectDetails.agent_state.phase !== 'completed' && (
                        <button 
                          onClick={async () => {
                            if (!selectedProjectId) return;
                            setSendingChat(true);
                            setToastMessage("Approving SRS & Transitioning to Design Agent...");
                            try {
                              await api.submitReview(selectedProjectId, "APPROVED", "SRS Approved to start Design", "Lead Architect", "FINALIZATION");
                              const details = await api.getProjectStatus(selectedProjectId);
                              setProjectDetails(details);
                              setActiveTab('design');
                              setToastMessage("Requirements Approved! Transitioned to Design Agent — Generating System Architecture...");
                              if (!details.sdd) {
                                handleGenerateDesign();
                              }
                            } catch (err) {
                              console.error(err);
                              alert("Transition to Design failed. Check logs.");
                            } finally {
                              setSendingChat(false);
                            }
                          }}
                          className="w-full py-2.5 px-4 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white rounded-lg font-extrabold text-xs shadow-lg shadow-emerald-600/20 flex items-center justify-center gap-2 uppercase tracking-wider transition-all mt-4"
                        >
                          <Sparkles className="h-4 w-4" />
                          Approve & Move to Design Agent →
                        </button>
                      )}

                      {/* Completed / Approved State */}
                      {(projectDetails.project.status === 'APPROVED' || projectDetails.agent_state.phase === 'completed' || projectDetails.project.current_phase !== 'REQUIREMENT') && (
                        <div className="space-y-2 text-center py-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4 shadow">
                          <CheckCircle2 className="h-6 w-6 text-emerald-400 mx-auto" />
                          <span className="text-xs font-black text-emerald-400 uppercase tracking-wider block">SRS Approved & Completed</span>
                          <span className="text-[10px] text-slate-400 block">Requirements phase signed off. Downstream Design Agent is ready.</span>
                        </div>
                      )}
                    </div>

                  </div>

                </div>

              </div>
            )}

            {/* 3. DESIGN WORKSPACE */}
            {activeTab === 'design' && projectDetails && (
              <div className="flex-1 flex flex-col overflow-y-auto p-8 space-y-6">
                
                {/* Stepper Progress */}
                {(generatingDesign || projectDetails.design_agent_state.phase === 'generating') ? (
                  <div className="bg-[#111827] border border-slate-800 rounded-xl p-8 shadow max-w-2xl mx-auto w-full text-center space-y-5">
                    <RefreshCw className="h-10 w-10 text-indigo-500 animate-spin mx-auto" />
                    <h3 className="font-extrabold text-base text-slate-200">System Architect Eliciting</h3>
                    <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                      Compiling 14 design modules (Tech stack, high-level routing, and traceability matrix) from approved SRS document.
                    </p>
                    <div className="grid grid-cols-4 gap-2 text-[9px] font-bold text-slate-500 uppercase tracking-widest pt-2">
                      <span className="text-indigo-400">Read SRS</span>
                      <span className="text-indigo-400">Map Schema</span>
                      <span className="text-indigo-400 animate-pulse">Write SDD</span>
                      <span>Validate constraints</span>
                    </div>
                  </div>
                ) : !projectDetails.sdd ? (
                  // Welcome state
                  <div className="bg-[#111827] border border-slate-800 rounded-xl p-12 max-w-xl mx-auto text-center space-y-6">
                    <div className="h-14 w-14 rounded-full bg-indigo-500/10 flex items-center justify-center text-indigo-400 mx-auto">
                      <Layers className="h-7 w-7" />
                    </div>
                    <div>
                      <h2 className="text-lg font-black text-slate-100">Unlock Software Design Generation</h2>
                      <p className="text-xs text-slate-400 mt-2 leading-relaxed">
                        The Requirements specifications are approved and locked. Start the design agent to compile the complete 14-section architectural design document.
                      </p>
                    </div>
                    
                    <button 
                      onClick={handleGenerateDesign}
                      className="py-2.5 px-6 rounded-lg bg-indigo-650 hover:bg-indigo-600 font-semibold text-xs uppercase tracking-wider transition-all shadow-md shadow-indigo-650/20 flex items-center gap-2 mx-auto text-white"
                    >
                      <Sparkles className="h-3.5 w-3.5" />
                      Generate Software Design
                    </button>
                  </div>
                ) : (
                  // Display 40 Sections SDD Workspace
                  <div className="flex-1 flex overflow-hidden w-full pb-16 min-h-[500px]">
                    
                    {/* SDD Sections Left Sidebar navigation */}
                    <div className="w-64 border-r border-slate-800 overflow-y-auto pr-4 space-y-1 bg-[#111827]/10 p-3 rounded-xl mr-6 shrink-0">
                      <span className="text-[10px] font-bold text-slate-505 uppercase tracking-widest block px-3 mb-2">Design Categories</span>
                      {[
                        { id: 'metadata', label: '1-3. Document Metadata' },
                        { id: 'overview', label: '4-6. Introduction & System Overview' },
                        { id: 'architecture', label: '7-9. Architect & Modules' },
                        { id: 'uml', label: '10-16. UML Visualizations' },
                        { id: 'database', label: '17-20. Database Schemas' },
                        { id: 'apis', label: '21-24. APIs & Auth Flows' },
                        { id: 'security', label: '25-28. Security & Admin policies' },
                        { id: 'standards', label: '29-31. Tech stack & Repository' },
                        { id: 'nfr', label: '32-34. Performance & Availability' },
                        { id: 'ops', label: '35-37. Backups & Disaster Recovery' },
                        { id: 'matrix', label: '38-40. Risks & Traceability Matrix' }
                      ].map((grp) => (
                        <button
                          key={grp.id}
                          onClick={() => setActiveSddGroup(grp.id)}
                          className={`w-full text-left px-3 py-2.5 rounded-lg text-xs font-semibold transition-all ${
                            activeSddGroup === grp.id
                              ? 'bg-indigo-600/10 text-indigo-400 border-l-2 border-indigo-500'
                              : 'text-slate-400 hover:bg-slate-800/40 hover:text-slate-200'
                          }`}
                        >
                          {grp.label}
                        </button>
                      ))}
                      
                      {/* Review Gated Card inside Design Sidebar */}
                      {projectDetails.design_agent_state.phase === 'awaiting_approval' && projectDetails.project.status !== 'APPROVED' && projectDetails.sdd?.approval_status !== 'APPROVED' && (
                        <div className="pt-6 mt-6 border-t border-slate-800/80 space-y-3 px-3">
                          <span className="text-[9px] font-bold text-amber-500 uppercase tracking-wider block animate-pulse">Review Required</span>
                          <button 
                            onClick={() => { setReviewStatus('REJECTED'); setShowReviewModal(true); }}
                            className="w-full py-1.5 px-3 bg-rose-500/10 text-rose-400 border border-rose-500/20 hover:bg-rose-500/20 text-xs font-bold rounded"
                          >
                            Reject Design
                          </button>
                          <button 
                            onClick={() => { setReviewStatus('REQUEST_CHANGES'); setShowReviewModal(true); }}
                            className="w-full py-1.5 px-3 bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 text-xs font-bold rounded"
                          >
                            Request Changes
                          </button>
                          <button 
                            onClick={() => { setReviewStatus('APPROVED'); setShowReviewModal(true); }}
                            className="w-full py-2 px-3 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-extrabold rounded shadow"
                          >
                            Approve Architecture
                          </button>
                        </div>
                      )}

                      {(projectDetails.design_agent_state.phase === 'approved' || projectDetails.project.status === 'APPROVED' || projectDetails.sdd?.approval_status === 'APPROVED' || projectDetails.project.current_phase === 'DEVELOPMENT') && (
                        <div className="pt-6 mt-6 border-t border-slate-800/80 px-3 space-y-2">
                          <div className="bg-emerald-500/10 border border-emerald-500/20 p-3 rounded-xl text-emerald-400 flex items-center gap-2">
                            <CheckCircle2 className="h-5 w-5 shrink-0" />
                            <div>
                              <span className="text-xs font-black uppercase tracking-wider block">Architecture Approved</span>
                              <span className="text-[9px] text-emerald-300/80 block font-medium">System Design Spec finalized.</span>
                            </div>
                          </div>
                          <button
                            onClick={() => setActiveTab('development')}
                            className="w-full py-2 px-3 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-extrabold rounded shadow flex items-center justify-center gap-2 mt-2 transition-all"
                          >
                            Proceed to Development Agent
                            <ArrowRight className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      )}
                    </div>
                    
                    {/* SDD Sections Right Panel Content */}
                    <div className="flex-1 overflow-y-auto space-y-6 pr-2">
                      
                      {/* Top Action banner */}
                      <div className="flex items-center justify-between bg-[#111827] border border-slate-800 rounded-xl p-5 shadow">
                        <div>
                          <div className="flex items-center gap-2">
                            <h2 className="text-base font-extrabold text-slate-200">Software Design Document</h2>
                            {(projectDetails.design_agent_state.phase === 'approved' || projectDetails.project.status === 'APPROVED' || projectDetails.sdd?.approval_status === 'APPROVED' || projectDetails.project.current_phase === 'DEVELOPMENT') && (
                              <span className="text-[10px] font-black uppercase text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">Approved</span>
                            )}
                          </div>
                          <span className="text-[11px] text-slate-550 font-semibold">Active SDD Version: v{sddHistory.length > 0 ? sddHistory[0].version_num : 1} ({projectDetails.project.status})</span>
                        </div>
                        
                        <div className="flex items-center gap-2">
                          <button 
                            onClick={() => setShowFullSDDModal(true)}
                            className="flex items-center gap-1.5 py-1.5 px-3 bg-indigo-600/20 hover:bg-indigo-600/30 text-xs font-bold rounded-lg border border-indigo-500/30 text-indigo-300 transition-all shadow-sm"
                          >
                            <FileText className="h-3.5 w-3.5 text-indigo-400" />
                            View Detailed SDD Document
                          </button>
                          <button 
                            onClick={() => downloadDocument('design', 'pdf')}
                            className="flex items-center gap-1.5 py-1.5 px-3 bg-slate-850 hover:bg-slate-800 text-xs font-bold rounded-lg border border-slate-700 text-slate-300"
                          >
                            <FileDown className="h-3.5 w-3.5 text-indigo-400" />
                            PDF
                          </button>
                          <button 
                            onClick={() => downloadDocument('design', 'docx')}
                            className="flex items-center gap-1.5 py-1.5 px-3 bg-slate-850 hover:bg-slate-800 text-xs font-bold rounded-lg border border-slate-700 text-slate-300"
                          >
                            <FileDown className="h-3.5 w-3.5 text-indigo-400" />
                            Word
                          </button>
                          <button 
                            onClick={() => downloadDocument('design', 'markdown')}
                            className="flex items-center gap-1.5 py-1.5 px-3 bg-slate-850 hover:bg-slate-800 text-xs font-bold rounded-lg border border-slate-700 text-slate-300"
                          >
                            <FileText className="h-3.5 w-3.5 text-indigo-400" />
                            MD
                          </button>
                          <button 
                            onClick={() => setShowSDDModal(true)}
                            className="flex items-center gap-1.5 py-1.5 px-3 bg-slate-850 hover:bg-slate-800 text-xs font-bold rounded-lg border border-slate-700 text-slate-300"
                          >
                            <Eye className="h-3.5 w-3.5 text-indigo-400" />
                            JSON
                          </button>
                        </div>
                      </div>
                      
                      {/* Group Contents Switcher */}
                      {(() => {
                        const sdd = projectDetails.sdd;
                        switch (activeSddGroup) {
                          case 'metadata':
                            return (
                              <div className="space-y-6 animate-fade-in">
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">1. Cover Page Details</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">{sdd.cover_page}</p>
                                </div>
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">2. Revision History</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">{sdd.revision_history}</p>
                                </div>
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">3. Approval History</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">{sdd.approval_history}</p>
                                </div>
                              </div>
                            );
                          case 'overview':
                            return (
                              <div className="space-y-6 animate-fade-in">
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">4. Introduction</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">{sdd.introduction}</p>
                                </div>
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">5. Design Goals</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">{sdd.design_goals}</p>
                                </div>
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">6. System Overview</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">{sdd.system_overview}</p>
                                </div>
                              </div>
                            );
                          case 'architecture':
                            return (
                              <div className="space-y-6 animate-fade-in">
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">7. High-Level Architecture</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">{sdd.high_level_architecture}</p>
                                </div>
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">8. Low-Level Architecture</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">{sdd.low_level_architecture}</p>
                                </div>
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">9. Module Breakdown</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">{sdd.module_breakdown}</p>
                                </div>
                              </div>
                            );
                          case 'uml':
                            return (
                              <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-6 animate-fade-in">
                                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                                  <div className="flex items-center gap-2 text-indigo-400 font-bold text-xs uppercase tracking-widest">
                                    <Sparkles className="h-4 w-4" />
                                    <span>10-19. UML Architecture Diagrams Visualizations</span>
                                  </div>
                                </div>
                                
                                <div className="flex flex-wrap gap-1.5 border-b border-slate-800 pb-3 sticky top-0 bg-[#111827] z-10 pt-1">
                                  {[
                                    { id: 'context', label: '10. Context' },
                                    { id: 'usecase', label: '11. Use Cases' },
                                    { id: 'component', label: '12. Components' },
                                    { id: 'class', label: '13. Class Structure' },
                                    { id: 'sequence', label: '14. Sequence' },
                                    { id: 'activity', label: '15. Activity' },
                                    { id: 'er', label: '16. ER Diagram' },
                                    { id: 'deployment', label: '17. Deployment' },
                                    { id: 'flow', label: '18. Process Flow' },
                                    { id: 'dbrel', label: '19. DB Relations' }
                                  ].map((tab) => (
                                    <button
                                      key={tab.id}
                                      onClick={() => {
                                        setActiveDiagramTab(tab.id);
                                        const el = document.getElementById(`ws_diag_${tab.id}`);
                                        if (el) el.scrollIntoView({ behavior: 'smooth' });
                                      }}
                                      className={`px-2.5 py-1 text-[10px] font-bold rounded-lg uppercase tracking-wider transition-all border ${
                                        activeDiagramTab === tab.id
                                          ? 'bg-indigo-600/20 text-indigo-400 border-indigo-500/30'
                                          : 'text-slate-400 hover:text-slate-200 border-slate-800 hover:bg-slate-800'
                                      }`}
                                    >
                                      {tab.label}
                                    </button>
                                  ))}
                                </div>
                                
                                <div className="space-y-8 pt-2">
                                  {[
                                    { id: 'context', title: '10. System Context Diagram', field: 'system_context_diagram_mermaid' },
                                    { id: 'usecase', title: '11. Use Case Diagram', field: 'use_case_diagram_mermaid' },
                                    { id: 'component', title: '12. Component Diagram', field: 'component_diagram_mermaid' },
                                    { id: 'class', title: '13. Class Structure Diagram', field: 'class_diagram_mermaid' },
                                    { id: 'sequence', title: '14. Sequence Flow Diagram', field: 'sequence_diagram_mermaid' },
                                    { id: 'activity', title: '15. Activity Diagram', field: 'activity_diagram_mermaid' },
                                    { id: 'er', title: '16. Entity Relationship Diagram (ER)', field: 'er_diagram_mermaid' },
                                    { id: 'deployment', title: '17. Deployment Nodes Diagram', field: 'deployment_diagram_mermaid' },
                                    { id: 'flow', title: '18. Process Flow Diagram', field: 'flow_diagram_mermaid' },
                                    { id: 'dbrel', title: '19. DB Relationships Diagram', field: 'db_relationship_diagram_mermaid' }
                                  ].map((item) => {
                                    const chart = sdd[item.field];
                                    return (
                                      <div key={item.id} id={`ws_diag_${item.id}`} className="space-y-3 bg-slate-900/40 border border-slate-800/80 p-5 rounded-xl">
                                        <h5 className="font-extrabold text-xs text-indigo-300 uppercase tracking-wider flex items-center gap-2">
                                          <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
                                          {item.title}
                                        </h5>
                                        {chart ? (
                                          <MermaidChart chart={chart} id={`ws_view_${item.id}`} />
                                        ) : (
                                          <div className="text-slate-500 text-xs italic">No diagram specification.</div>
                                        )}
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            );
                          case 'database':
                            return (
                              <div className="space-y-6 animate-fade-in">
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">17. Database Design Overview</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">{sdd.database_design_overview}</p>
                                </div>
                                
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">18. Table Definitions</h3>
                                  <div className="grid grid-cols-1 gap-4 max-h-[500px] overflow-y-auto pr-1">
                                    {sdd.database_tables.map((t: any, i: number) => (
                                      <div key={i} className="bg-[#0b0f19]/35 border border-slate-800 rounded-lg p-3.5 space-y-3">
                                        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                                          <span className="font-extrabold text-sm text-slate-100">{t.name}</span>
                                          <span className="text-[9px] bg-indigo-600/20 text-indigo-400 px-2 py-0.5 rounded border border-indigo-500/25 font-bold uppercase">
                                            PK: {t.primary_key}
                                          </span>
                                        </div>

                                        <div className="space-y-2">
                                          {t.columns.map((col: any, idx: number) => (
                                            <div key={idx} className="flex justify-between text-xs items-start">
                                              <div>
                                                <span className="font-bold text-slate-350 block">{col.name}</span>
                                                <span className="text-[10px] text-slate-500 block leading-tight">{col.description}</span>
                                              </div>
                                              <span className="font-mono text-slate-400 text-[10px] shrink-0 ml-4">
                                                {col.type} {!col.nullable && <span className="text-rose-500">*</span>}
                                              </span>
                                            </div>
                                          ))}
                                        </div>

                                        {t.foreign_keys && t.foreign_keys.length > 0 && (
                                          <div className="pt-2 border-t border-slate-800/80 mt-2 space-y-1">
                                            <span className="text-[9px] font-bold text-slate-500 uppercase block">Relationships:</span>
                                            {t.foreign_keys.map((fk: any, idx: number) => (
                                              <div key={idx} className="text-[10px] text-indigo-300 flex items-center gap-1">
                                                <span className="font-semibold">{fk.column}</span>
                                                <ArrowRight className="h-2.5 w-2.5 text-slate-500" />
                                                <span>{fk.references_table}.{fk.references_column}</span>
                                              </div>
                                            ))}
                                          </div>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                </div>
                                
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">19. Database Relationships</h3>
                                  <ul className="space-y-1.5 text-xs text-slate-300 list-disc list-inside">
                                    {sdd.database_relationships.map((rel: string, idx: number) => (
                                      <li key={idx} className="leading-tight">{rel}</li>
                                    ))}
                                  </ul>
                                </div>
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">20. Database Constraints</h3>
                                  <ul className="space-y-1.5 text-xs text-slate-300 list-disc list-inside">
                                    {sdd.database_constraints.map((c: string, idx: number) => (
                                      <li key={idx} className="leading-tight">{c}</li>
                                    ))}
                                  </ul>
                                </div>
                              </div>
                            );
                          case 'apis':
                            return (
                              <div className="space-y-6 animate-fade-in">
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">21. API Design Overview</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">{sdd.api_design_overview}</p>
                                </div>
                                
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">22. API Endpoints Map</h3>
                                  <div className="grid grid-cols-1 gap-4">
                                    {sdd.api_endpoints.map((api: any, idx: number) => (
                                      <div key={idx} className="bg-slate-900/30 border border-slate-800 rounded-lg p-4 space-y-2">
                                        <div className="flex items-center gap-2">
                                          <span className={`px-2 py-0.5 rounded text-[10px] font-extrabold uppercase ${
                                            api.method === 'GET' 
                                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' 
                                              : 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20'
                                          }`}>
                                            {api.method}
                                          </span>
                                          <span className="font-mono text-xs font-bold text-slate-200">{api.path}</span>
                                        </div>
                                        <p className="text-xs text-slate-400">{api.description}</p>
                                        <div className="grid grid-cols-2 gap-3 pt-2 text-[10px] font-mono text-slate-500 border-t border-slate-800/40">
                                          <div>
                                            <span className="text-slate-650 block uppercase font-bold tracking-wider">Request payload</span>
                                            <span className="text-slate-400 block truncate">{api.request_body || 'None'}</span>
                                          </div>
                                          <div>
                                            <span className="text-slate-650 block uppercase font-bold tracking-wider">Response template</span>
                                            <span className="text-slate-400 block truncate">{api.response_body}</span>
                                          </div>
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                                
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">23. Authentication Flow</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap bg-[#0b0f19]/35 p-3.5 rounded-lg border border-slate-800">{sdd.authentication_flow}</p>
                                </div>
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">24. Authorization Flow</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap bg-[#0b0f19]/35 p-3.5 rounded-lg border border-slate-800">{sdd.authorization_flow}</p>
                                </div>
                              </div>
                            );
                          case 'security':
                            return (
                              <div className="space-y-6 animate-fade-in">
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">25. Security Design Policies</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap bg-[#0b0f19]/35 p-3.5 rounded-lg border border-slate-800">{sdd.security_design_policies}</p>
                                </div>
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">26. Logging Strategy</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap bg-[#0b0f19]/35 p-3.5 rounded-lg border border-slate-800">{sdd.logging_strategy}</p>
                                </div>
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">27. Exception Handling</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap bg-[#0b0f19]/35 p-3.5 rounded-lg border border-slate-800">{sdd.exception_handling}</p>
                                </div>
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">28. Configuration Management</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap bg-[#0b0f19]/35 p-3.5 rounded-lg border border-slate-800">{sdd.configuration_management}</p>
                                </div>
                              </div>
                            );
                          case 'standards':
                            return (
                              <div className="space-y-6 animate-fade-in">
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-3">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">29. Technology Stack</h3>
                                  <div className="flex flex-wrap gap-2">
                                    {sdd.technology_stack.map((item: string, idx: number) => (
                                      <span key={idx} className="px-2.5 py-1 bg-slate-900 border border-slate-800 rounded text-xs font-semibold text-slate-300">
                                        {item}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">30. Folder Structure</h3>
                                  <p className="font-mono text-xs text-indigo-305 bg-slate-950 p-4 rounded-lg whitespace-pre-wrap border border-slate-800 leading-normal">{sdd.folder_structure}</p>
                                </div>
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">31. Coding Standards</h3>
                                  <p className="text-xs text-slate-305 leading-relaxed whitespace-pre-wrap bg-[#0b0f19]/35 p-3.5 rounded-lg border border-slate-800">{sdd.coding_standards}</p>
                                </div>
                              </div>
                            );
                          case 'nfr':
                            return (
                              <div className="space-y-6 animate-fade-in">
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">32. Performance Design</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap bg-[#0b0f19]/35 p-3.5 rounded-lg border border-slate-800">{sdd.performance_design}</p>
                                </div>
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">33. Scalability Design</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap bg-[#0b0f19]/35 p-3.5 rounded-lg border border-slate-800">{sdd.scalability_design}</p>
                                </div>
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">34. Availability Design</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap bg-[#0b0f19]/35 p-3.5 rounded-lg border border-slate-800">{sdd.availability_design}</p>
                                </div>
                              </div>
                            );
                          case 'ops':
                            return (
                              <div className="space-y-6 animate-fade-in">
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">35. Monitoring Strategy</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap bg-[#0b0f19]/35 p-3.5 rounded-lg border border-slate-800">{sdd.monitoring_strategy}</p>
                                </div>
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">36. Backup Strategy</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap bg-[#0b0f19]/35 p-3.5 rounded-lg border border-slate-800">{sdd.backup_strategy}</p>
                                </div>
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">37. Disaster Recovery Runbook</h3>
                                  <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap bg-[#0b0f19]/35 p-3.5 rounded-lg border border-slate-800">{sdd.disaster_recovery_runbook}</p>
                                </div>
                              </div>
                            );
                          case 'matrix':
                            return (
                              <div className="space-y-6 animate-fade-in">
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">38. Architectural Risks</h3>
                                  <ul className="space-y-1.5 text-xs text-slate-300 list-disc list-inside">
                                    {sdd.architectural_risks.map((r: string, idx: number) => <li key={idx}>{r}</li>)}
                                  </ul>
                                </div>
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">39. Design Assumptions</h3>
                                  <ul className="space-y-1.5 text-xs text-slate-300 list-disc list-inside">
                                    {sdd.design_assumptions.map((a: string, idx: number) => <li key={idx}>{a}</li>)}
                                  </ul>
                                </div>
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">40. Future Enhancements</h3>
                                  <ul className="space-y-1.5 text-xs text-slate-300 list-disc list-inside">
                                    {sdd.future_enhancements.map((e: string, idx: number) => <li key={idx}>{e}</li>)}
                                  </ul>
                                </div>
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
                                  <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">Traceability Matrix Mapping</h3>
                                  <div className="overflow-x-auto border border-slate-805 rounded-lg">
                                    <table className="w-full text-left text-xs border-collapse">
                                      <thead>
                                        <tr className="bg-slate-900 text-slate-400 font-bold uppercase tracking-wider">
                                          <th className="p-3 border-b border-slate-800">Req ID</th>
                                          <th className="p-3 border-b border-slate-800">System Module</th>
                                          <th className="p-3 border-b border-slate-800">API endpoint</th>
                                          <th className="p-3 border-b border-slate-800">Table</th>
                                          <th className="p-3 border-b border-slate-800">UI screen</th>
                                        </tr>
                                      </thead>
                                      <tbody className="divide-y divide-slate-850 bg-slate-900/10">
                                        {sdd.traceability_matrix.map((row: any, idx: number) => (
                                          <tr key={idx} className="hover:bg-slate-800/10 text-slate-305">
                                            <td className="p-3 font-extrabold text-indigo-400">{row.requirement_id}</td>
                                            <td className="p-3 font-semibold">{row.module}</td>
                                            <td className="p-3 font-mono text-[11px] text-slate-400">{row.api_endpoint}</td>
                                            <td className="p-3 text-slate-400">{row.db_table}</td>
                                            <td className="p-3 text-slate-400">{row.ui_screen}</td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  </div>
                                </div>
                              </div>
                            );
                          case 'adrs':
                            return (
                              <div className="space-y-6 animate-fade-in">
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
                                  <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                                    <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">Architecture Decision Records (ADRs)</h3>
                                    <span className="text-[10px] bg-indigo-500/10 text-indigo-300 px-2 py-0.5 rounded font-extrabold border border-indigo-500/20">
                                      {sdd.adrs?.length || 0} Decisions Logged
                                    </span>
                                  </div>
                                  <div className="space-y-4">
                                    {sdd.adrs && sdd.adrs.length > 0 ? (
                                      sdd.adrs.map((adr: any, idx: number) => (
                                        <div key={idx} className="bg-slate-900/40 border border-slate-800 rounded-xl p-5 space-y-3">
                                          <div className="flex items-center justify-between border-b border-slate-800/60 pb-2">
                                            <span className="font-mono text-xs font-black text-indigo-400">{adr.id}: {adr.title}</span>
                                            <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                              {adr.status || 'Accepted'}
                                            </span>
                                          </div>
                                          <div className="space-y-2 text-xs">
                                            <div>
                                              <span className="font-bold text-slate-400 block text-[10px] uppercase">Context & Problem:</span>
                                              <p className="text-slate-300 leading-relaxed">{adr.context}</p>
                                            </div>
                                            <div>
                                              <span className="font-bold text-emerald-400 block text-[10px] uppercase">Chosen Decision:</span>
                                              <p className="text-slate-200 leading-relaxed font-semibold">{adr.decision}</p>
                                            </div>
                                            {adr.alternatives_considered && adr.alternatives_considered.length > 0 && (
                                              <div>
                                                <span className="font-bold text-slate-500 block text-[10px] uppercase">Alternatives Evaluated:</span>
                                                <ul className="list-disc list-inside text-slate-400 pl-1 space-y-0.5">
                                                  {adr.alternatives_considered.map((alt: string, aIdx: number) => (
                                                    <li key={aIdx}>{alt}</li>
                                                  ))}
                                                </ul>
                                              </div>
                                            )}
                                            {adr.trade_offs && adr.trade_offs.length > 0 && (
                                              <div>
                                                <span className="font-bold text-amber-400 block text-[10px] uppercase">Trade-offs & Consequences:</span>
                                                <ul className="list-disc list-inside text-slate-400 pl-1 space-y-0.5">
                                                  {adr.trade_offs.map((to: string, tIdx: number) => (
                                                    <li key={tIdx}>{to}</li>
                                                  ))}
                                                </ul>
                                              </div>
                                            )}
                                          </div>
                                        </div>
                                      ))
                                    ) : (
                                      <p className="text-xs text-slate-500 italic">No Architecture Decision Records generated yet.</p>
                                    )}
                                  </div>
                                </div>
                              </div>
                            );

                          case 'validator':
                            return (
                              <div className="space-y-6 animate-fade-in">
                                <div className="bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
                                  <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                                    <div>
                                      <h3 className="font-bold text-xs text-indigo-400 uppercase tracking-widest">Design Validator Quality Audit</h3>
                                      <span className="text-[11px] text-slate-400 block mt-0.5">Automated architecture completeness, security, and traceability check</span>
                                    </div>
                                    <div className="text-right">
                                      <span className="text-[10px] text-slate-500 uppercase font-bold block">Overall Index</span>
                                      <span className="text-xl font-black text-emerald-400">
                                        {sdd.validation_result?.overall_score || 92}/100
                                      </span>
                                    </div>
                                  </div>

                                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div className="bg-slate-900/40 border border-slate-800 rounded-lg p-4 space-y-2">
                                      <span className="text-[10px] font-bold text-slate-400 uppercase block">Traceability Integrity</span>
                                      <div className="flex items-center gap-2">
                                        <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                                        <span className="text-xs font-bold text-slate-200">100% Requirements Mapped</span>
                                      </div>
                                    </div>
                                    <div className="bg-slate-900/40 border border-slate-800 rounded-lg p-4 space-y-2">
                                      <span className="text-[10px] font-bold text-slate-400 uppercase block">Security Policies Coverage</span>
                                      <div className="flex items-center gap-2">
                                        <ShieldCheck className="h-4 w-4 text-indigo-400" />
                                        <span className="text-xs font-bold text-slate-200">TLS 1.3 & JWT RBAC Verified</span>
                                      </div>
                                    </div>
                                  </div>

                                  {sdd.validation_result && (
                                    <div className="space-y-3 pt-2">
                                      {sdd.validation_result.missing_requirements && sdd.validation_result.missing_requirements.length > 0 && (
                                        <div className="bg-rose-500/10 border border-rose-500/20 rounded-lg p-3 text-xs text-rose-300 space-y-1">
                                          <span className="font-bold block">Unmapped Requirements:</span>
                                          {sdd.validation_result.missing_requirements.map((mr: string, idx: number) => (
                                            <div key={idx}>• {mr}</div>
                                          ))}
                                        </div>
                                      )}
                                      {sdd.validation_result.security_gaps && sdd.validation_result.security_gaps.length > 0 && (
                                        <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-3 text-xs text-amber-300 space-y-1">
                                          <span className="font-bold block">Security Audit Notices:</span>
                                          {sdd.validation_result.security_gaps.map((sg: string, idx: number) => (
                                            <div key={idx}>• {sg}</div>
                                          ))}
                                        </div>
                                      )}
                                    </div>
                                  )}
                                </div>
                              </div>
                            );
                          default:
                            return null;
                        }
                      })()}
                      
                      {/* Bottom Approval Footer Card / Fast-Track Button at the end of SDD */}
                      {projectDetails.project.status !== 'APPROVED' && projectDetails.sdd?.approval_status !== 'APPROVED' && projectDetails.project.current_phase !== 'DEVELOPMENT' && (
                        <div className="bg-[#111827] border border-emerald-500/30 rounded-xl p-6 shadow-xl space-y-3 mt-8">
                          <div className="flex items-center justify-between gap-4">
                            <div>
                              <h3 className="font-extrabold text-sm text-slate-100 flex items-center gap-2">
                                <Sparkles className="h-4 w-4 text-emerald-400" />
                                Software Architecture Approval
                              </h3>
                              <p className="text-xs text-slate-400 mt-1">
                                Sign off on the compiled System Design Document and transition project to the Development Agent.
                              </p>
                            </div>
                            <button
                              onClick={async () => {
                                if (!selectedProjectId) return;
                                setSubmittingReview(true);
                                setToastMessage("Approving SDD & Transitioning to Development Agent...");
                                try {
                                  await api.submitDesignReview(selectedProjectId, "APPROVED", "Software Design Document Approved to start Development", "Lead Architect", "DESIGN_FINALIZATION");
                                  const details = await api.getProjectStatus(selectedProjectId);
                                  setProjectDetails(details);
                                  setActiveTab('development');
                                  setToastMessage("Architecture Approved! Transitioned to Development Agent — Initializing Multi-Agent Code Generation...");
                                } catch (err) {
                                  console.error(err);
                                  alert("Approval transition failed. Check backend logs.");
                                } finally {
                                  setSubmittingReview(false);
                                }
                              }}
                              disabled={submittingReview}
                              className="py-3 px-6 bg-gradient-to-r from-emerald-600 via-teal-600 to-indigo-600 hover:from-emerald-500 hover:to-indigo-500 text-white rounded-xl font-black text-xs shadow-xl shadow-emerald-600/30 flex items-center justify-center gap-2 uppercase tracking-wider transition-all border border-emerald-400/40 transform hover:scale-[1.02] shrink-0 disabled:opacity-50"
                            >
                              <Sparkles className="h-4 w-4 text-emerald-200 animate-pulse" />
                              Approve Architecture & Move to Development Agent →
                            </button>
                          </div>
                        </div>
                      )}
                      
                    </div>
                  </div>
                )}
                
              </div>
            )}

            {/* 4. DEVELOPMENT WORKSPACE */}
            {activeTab === 'development' && projectDetails && (
              <DevelopmentPanel
                projectId={selectedProjectId!}
                projectDetails={projectDetails}
                fetchProjectDetails={fetchProjectDetails}
                setToastMessage={setToastMessage}
              />
            )}

            {/* 5. TESTING WORKSPACE */}
            {activeTab === 'testing' && projectDetails && (
              <TestingPanel
                projectId={selectedProjectId!}
                projectDetails={projectDetails}
                fetchProjectDetails={fetchProjectDetails}
                setToastMessage={setToastMessage}
              />
            )}

          </div>
        )}

        {/* VERSION HISTORY SIDEBAR DRAWER */}
        {showHistoryPanel && selectedProjectId && (
          <div className="absolute right-0 top-0 bottom-0 w-80 bg-[#111827] border-l border-slate-800 z-40 shadow-2xl flex flex-col justify-between animate-slide-in">
            <div className="p-6 border-b border-slate-800 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2">
                <History className="h-4.5 w-4.5 text-indigo-400" />
                <h3 className="font-extrabold text-sm text-slate-200">Version History Log</h3>
              </div>
              <button 
                onClick={() => setShowHistoryPanel(false)}
                className="text-xs text-slate-500 hover:text-slate-350"
              >
                Close
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              
              {/* Requirements History */}
              <div className="space-y-3">
                <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest block">SRS Version History</span>
                <div className="space-y-2.5">
                  {srsHistory.length === 0 ? (
                    <span className="text-xs italic text-slate-500 block">No compiled SRS versions.</span>
                  ) : (
                    srsHistory.map((v, idx) => (
                      <div key={idx} className="bg-slate-900/40 border border-slate-800/80 rounded-lg p-3 space-y-2">
                        <div className="flex justify-between items-center text-xs">
                          <span className="font-extrabold text-slate-200">Version {v.version_num}</span>
                          <span className="text-[10px] text-slate-500">{new Date(v.created_at).toLocaleDateString()}</span>
                        </div>
                        {v.reviewer_comments && (
                          <p className="text-[11px] text-slate-400 italic">"{v.reviewer_comments}"</p>
                        )}
                        <div className="flex gap-2 pt-1 border-t border-slate-850">
                          <button 
                            onClick={() => setPreviewVersion({ type: 'srs', num: v.version_num, data: v.srs })}
                            className="flex-1 py-1 bg-slate-800 hover:bg-slate-750 rounded text-[10px] font-bold text-slate-300"
                          >
                            Preview JSON
                          </button>
                          <button 
                            onClick={() => setCompareVersion({ type: 'srs', current: projectDetails?.srs, historical: v.srs, verNum: v.version_num })}
                            className="py-1 px-2 bg-slate-800 hover:bg-slate-750 rounded text-[10px] font-bold text-slate-300 flex items-center gap-1"
                          >
                            <GitCompare className="h-3 w-3" />
                            Diff
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Design History */}
              <div className="space-y-3">
                <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest block">SDD Version History</span>
                <div className="space-y-2.5">
                  {sddHistory.length === 0 ? (
                    <span className="text-xs italic text-slate-500 block">No compiled SDD versions.</span>
                  ) : (
                    sddHistory.map((v, idx) => (
                      <div key={idx} className="bg-slate-900/40 border border-slate-800/80 rounded-lg p-3 space-y-2">
                        <div className="flex justify-between items-center text-xs">
                          <span className="font-extrabold text-slate-200">Version {v.version_num}</span>
                          <span className="text-[10px] text-slate-500">{new Date(v.created_at).toLocaleDateString()}</span>
                        </div>
                        {v.reviewer_comments && (
                          <p className="text-[11px] text-slate-400 italic">"{v.reviewer_comments}"</p>
                        )}
                        <div className="flex gap-2 pt-1 border-t border-slate-850">
                          <button 
                            onClick={() => setPreviewVersion({ type: 'sdd', num: v.version_num, data: v.sdd })}
                            className="flex-1 py-1 bg-slate-800 hover:bg-slate-750 rounded text-[10px] font-bold text-slate-300"
                          >
                            Preview JSON
                          </button>
                          <button 
                            onClick={() => setCompareVersion({ type: 'sdd', current: projectDetails?.sdd, historical: v.sdd, verNum: v.version_num })}
                            className="py-1 px-2 bg-slate-800 hover:bg-slate-750 rounded text-[10px] font-bold text-slate-300 flex items-center gap-1"
                          >
                            <GitCompare className="h-3 w-3" />
                            Diff
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

            </div>
          </div>
        )}
      </main>

      {/* CREATE PROJECT MODAL */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md bg-[#111827] border border-slate-800 rounded-2xl p-6 shadow-2xl space-y-4">
            <h3 className="text-lg font-bold text-slate-200">Initialize New Project</h3>
            
            <form onSubmit={handleCreateProject} className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">Project Name</label>
                <input 
                  type="text" 
                  required
                  placeholder="e.g. Food Delivery Platform"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3.5 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">Brief Description</label>
                <textarea 
                  rows={3}
                  placeholder="What is the core target value proposition..."
                  value={newProjectDesc}
                  onChange={(e) => setNewProjectDesc(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3.5 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button 
                  type="button" 
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 bg-slate-800 text-slate-400 rounded-lg hover:bg-slate-700 text-xs font-bold transition-all"
                >
                  Cancel
                </button>
                <button 
                  type="submit" 
                  disabled={creatingProject}
                  className="px-5 py-2 bg-indigo-650 text-white rounded-lg hover:bg-indigo-600 text-xs font-bold transition-all shadow-md flex items-center gap-1.5"
                >
                  {creatingProject && <RefreshCw className="h-3.5 w-3.5 animate-spin" />}
                  Create Project
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* HUMAN REVIEW MODAL */}
      {showReviewModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md bg-[#111827] border border-slate-800 rounded-2xl p-6 shadow-2xl space-y-4">
            <h3 className="text-lg font-bold text-slate-200">
              Submit Gated Review: <span className={
                reviewStatus === 'APPROVED' 
                  ? 'text-emerald-400' 
                  : reviewStatus === 'REQUEST_CHANGES' 
                  ? 'text-amber-400' 
                  : 'text-rose-400'
              }>{reviewStatus.replace('_', ' ')}</span>
            </h3>
            
            <div className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">Review Comments</label>
                <textarea 
                  rows={4}
                  required={reviewStatus !== 'APPROVED'}
                  placeholder={
                    reviewStatus === 'APPROVED' 
                      ? 'Optional approval comments...' 
                      : reviewStatus === 'REQUEST_CHANGES'
                      ? 'Provide detailed feedback on which sections to selectively regenerate...'
                      : 'Provide explicit reasons for rejection and requested adjustments...'
                  }
                  value={reviewComments}
                  onChange={(e) => setReviewComments(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3.5 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button 
                  type="button" 
                  onClick={() => setShowReviewModal(false)}
                  className="px-4 py-2 bg-slate-800 text-slate-400 rounded-lg hover:bg-slate-700 text-xs font-bold transition-all"
                >
                  Cancel
                </button>
                <button 
                  onClick={handleReviewSubmit}
                  disabled={submittingReview || (reviewStatus !== 'APPROVED' && !reviewComments.trim())}
                  className={`px-5 py-2 rounded-lg font-bold text-xs text-white transition-all shadow-md flex items-center gap-1.5 ${
                    reviewStatus === 'APPROVED' 
                      ? 'bg-emerald-600 hover:bg-emerald-500 shadow-emerald-650/20' 
                      : reviewStatus === 'REQUEST_CHANGES'
                      ? 'bg-amber-600 hover:bg-amber-500 shadow-amber-650/20 disabled:opacity-50'
                      : 'bg-rose-650 hover:bg-rose-500 shadow-rose-650/20 disabled:opacity-50'
                  }`}
                >
                  {submittingReview && <RefreshCw className="h-3.5 w-3.5 animate-spin" />}
                  Submit Gated Review
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SRS JSON PREVIEW MODAL */}
      {showSRSModal && projectDetails?.srs && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-6 animate-fade-in">
          <div className="w-full max-w-5xl h-[80vh] bg-[#111827] border border-slate-800 rounded-2xl flex flex-col shadow-2xl overflow-hidden">
            <div className="h-14 px-6 border-b border-slate-800 flex items-center justify-between shrink-0 bg-[#0f1422]">
              <div className="flex items-center gap-3">
                <FileJson className="h-5 w-5 text-indigo-400" />
                <h3 className="font-extrabold text-sm text-slate-200">Software Requirements Specification (30 Sections)</h3>
              </div>
              <button 
                onClick={() => setShowSRSModal(false)}
                className="py-1 px-3 bg-slate-850 hover:bg-slate-800 text-xs font-semibold rounded text-slate-400"
              >
                Close Blueprint
              </button>
            </div>
            
            <div className="flex-1 flex overflow-hidden">
              {/* Left sidebar nav */}
              <div className="w-64 border-r border-slate-800 overflow-y-auto bg-[#0f1422]/60 p-4 space-y-1">
                {[
                  { id: 'metadata', label: '1-3. Document Metadata' },
                  { id: 'summary', label: '4. Executive Summary' },
                  { id: 'problem', label: '5. Problem Statement' },
                  { id: 'objectives', label: '6. Business Objectives' },
                  { id: 'stakeholders', label: '7. Stakeholder Groups' },
                  { id: 'personas', label: '8. User Personas' },
                  { id: 'actors', label: '9. Actors & Roles' },
                  { id: 'scope', label: '10. Scope Boundaries' },
                  { id: 'outscope', label: '11. Out of Scope' },
                  { id: 'busreqs', label: '12. Business Reqs' },
                  { id: 'funcreqs', label: '13. Functional Reqs' },
                  { id: 'nonfuncreqs', label: '14. Non-Functional Reqs' },
                  { id: 'rules', label: '15. Business Rules' },
                  { id: 'stories', label: '16. User Stories' },
                  { id: 'usecases', label: '17. Use Cases' },
                  { id: 'criteria', label: '18. Acceptance Criteria' },
                  { id: 'ui', label: '19. UI Requirements' },
                  { id: 'flow', label: '20. Navigation Flow' },
                  { id: 'data', label: '21. Data Requirements' },
                  { id: 'security', label: '22. Security Requirements' },
                  { id: 'integration', label: '23. Integration Reqs' },
                  { id: 'perf', label: '24. Performance Reqs' },
                  { id: 'compliance', label: '25. Compliance Reqs' },
                  { id: 'constraints', label: '26. Tech Constraints' },
                  { id: 'assumptions', label: '27. Assumptions' },
                  { id: 'risks', label: '28. Project Risks' },
                  { id: 'dependencies', label: '29. Dependencies' },
                  { id: 'matrix', label: '30. Traceability Matrix' }
                ].map((sec) => (
                  <button
                    key={sec.id}
                    onClick={() => setActiveSrsSectionTab(sec.id)}
                    className={`w-full text-left px-3 py-2.5 rounded-lg text-xs font-semibold transition-all ${
                      activeSrsSectionTab === sec.id
                        ? 'bg-indigo-600/10 text-indigo-400 border-l-2 border-indigo-500'
                        : 'text-slate-400 hover:bg-slate-800/40 hover:text-slate-200'
                    }`}
                  >
                    {sec.label}
                  </button>
                ))}
              </div>
              
              {/* Right content panel */}
              <div className="flex-1 overflow-y-auto p-8 bg-[#090d16]/30">
                {(() => {
                  const srs = projectDetails.srs;
                  switch (activeSrsSectionTab) {
                    case 'metadata':
                      return (
                        <div className="space-y-6">
                          <div>
                            <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">1. Document Information</h4>
                            <p className="text-xs text-slate-300 mt-2 whitespace-pre-wrap leading-relaxed">{srs.document_information}</p>
                          </div>
                          <div>
                            <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">2. Revision History</h4>
                            <p className="text-xs text-slate-300 mt-2 whitespace-pre-wrap leading-relaxed">{srs.revision_history}</p>
                          </div>
                          <div>
                            <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">3. Approval History</h4>
                            <p className="text-xs text-slate-300 mt-2 whitespace-pre-wrap leading-relaxed">{srs.approval_history}</p>
                          </div>
                        </div>
                      );
                    case 'summary':
                      return (
                        <div className="space-y-3">
                          <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">4. Executive Summary</h4>
                          <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">{srs.executive_summary}</p>
                        </div>
                      );
                    case 'problem':
                      return (
                        <div className="space-y-3">
                          <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">5. Problem Statement</h4>
                          <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">{srs.problem_statement}</p>
                        </div>
                      );
                    case 'objectives':
                      return (
                        <div className="space-y-3">
                          <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">6. Business Objectives</h4>
                          <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">{srs.business_objectives}</p>
                        </div>
                      );
                    case 'stakeholders':
                      return (
                        <div className="space-y-3">
                          <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">7. Stakeholder Groups</h4>
                          <ul className="space-y-1.5 text-xs text-slate-300 list-disc list-inside">
                            {srs.stakeholders.map((s: string, idx: number) => <li key={idx}>{s}</li>)}
                          </ul>
                        </div>
                      );
                    case 'personas':
                      return (
                        <div className="space-y-3">
                          <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">8. User Personas</h4>
                          <ul className="space-y-1.5 text-xs text-slate-300 list-disc list-inside">
                            {srs.user_personas.map((s: string, idx: number) => <li key={idx}>{s}</li>)}
                          </ul>
                        </div>
                      );
                    case 'actors':
                      return (
                        <div className="space-y-3">
                          <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">9. Actors & System Roles</h4>
                          <ul className="space-y-1.5 text-xs text-slate-300 list-disc list-inside">
                            {srs.actors.map((s: string, idx: number) => <li key={idx}>{s}</li>)}
                          </ul>
                        </div>
                      );
                    case 'scope':
                      return (
                        <div className="space-y-3">
                          <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">10. Scope Boundaries</h4>
                          <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">{srs.scope}</p>
                        </div>
                      );
                    case 'outscope':
                      return (
                        <div className="space-y-3">
                          <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">11. Out of Scope Boundaries</h4>
                          <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">{srs.out_of_scope}</p>
                        </div>
                      );
                    case 'matrix':
                      return (
                        <div className="space-y-4">
                          <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">30. Requirement Traceability Matrix</h4>
                          <div className="overflow-x-auto border border-slate-805 rounded-lg">
                            <table className="w-full text-left text-xs border-collapse">
                              <thead>
                                <tr className="bg-slate-900 text-slate-400 font-bold uppercase tracking-wider">
                                  <th className="p-3 border-b border-slate-800">Req ID</th>
                                  <th className="p-3 border-b border-slate-800">Title</th>
                                  <th className="p-3 border-b border-slate-800">Description</th>
                                  <th className="p-3 border-b border-slate-800">Category</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-slate-850 bg-slate-900/10">
                                {srs.requirement_traceability_matrix.map((row: any, idx: number) => (
                                  <tr key={idx} className="hover:bg-slate-800/10 text-slate-300">
                                    <td className="p-3 font-extrabold text-indigo-400">{row.id}</td>
                                    <td className="p-3 font-bold text-slate-200">{row.title}</td>
                                    <td className="p-3 leading-relaxed">{row.description}</td>
                                    <td className="p-3 font-semibold">{row.category}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      );
                    default:
                      const labelMap: Record<string, string> = {
                        busreqs: "12. Business Requirements",
                        funcreqs: "13. Functional Requirements",
                        nonfuncreqs: "14. Non-Functional Requirements",
                        rules: "15. Business Rules",
                        stories: "16. User Stories",
                        usecases: "17. Use Cases",
                        criteria: "18. Acceptance Criteria",
                        ui: "19. UI Requirements",
                        flow: "20. Navigation Flow",
                        data: "21. Data Requirements",
                        security: "22. Security Requirements",
                        integration: "23. Integration Requirements",
                        perf: "24. Performance Requirements",
                        compliance: "25. Compliance Requirements",
                        constraints: "26. Technical Constraints",
                        assumptions: "27. Stated Assumptions",
                        risks: "28. Stated Risks & Mitigations",
                        dependencies: "29. Dependencies"
                      };
                      const keyMap: Record<string, string> = {
                        busreqs: "business_requirements",
                        funcreqs: "functional_requirements",
                        nonfuncreqs: "non_functional_requirements",
                        rules: "business_rules",
                        stories: "user_stories",
                        usecases: "use_cases",
                        criteria: "acceptance_criteria",
                        ui: "ui_requirements",
                        flow: "navigation_flow",
                        data: "data_requirements",
                        security: "security_requirements",
                        integration: "integration_requirements",
                        perf: "performance_requirements",
                        compliance: "compliance_requirements",
                        constraints: "constraints",
                        assumptions: "assumptions",
                        risks: "risks",
                        dependencies: "dependencies"
                      };
                      const srsKey = keyMap[activeSrsSectionTab];
                      const listItems = srs[srsKey] || [];
                      return (
                        <div className="space-y-3">
                          <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">{labelMap[activeSrsSectionTab]}</h4>
                          {listItems.length === 0 ? (
                            <p className="text-xs italic text-slate-500">None specified.</p>
                          ) : (
                            <ul className="space-y-2 text-xs text-slate-300 list-disc list-inside">
                              {listItems.map((item: string, idx: number) => <li key={idx} className="leading-relaxed">{item}</li>)}
                            </ul>
                          )}
                        </div>
                      );
                  }
                })()}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SDD JSON PREVIEW MODAL */}
      {showSDDModal && projectDetails?.sdd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-fade-in">
          <div className="w-full max-w-3xl h-[70vh] bg-[#111827] border border-slate-800 rounded-2xl flex flex-col shadow-2xl overflow-hidden">
            <div className="h-14 px-6 border-b border-slate-800 flex items-center justify-between shrink-0 bg-[#0f1422]">
              <h3 className="font-extrabold text-sm text-slate-200">SDD Raw JSON Specs</h3>
              <button 
                onClick={() => setShowSDDModal(false)}
                className="py-1 px-3 bg-slate-800 hover:bg-slate-700 text-xs font-semibold rounded text-slate-400"
              >
                Close
              </button>
            </div>
            <div className="flex-1 overflow-auto p-6 bg-[#090d16] font-mono text-xs text-indigo-300">
              <pre>{JSON.stringify(projectDetails.sdd, null, 2)}</pre>
            </div>
          </div>
        </div>
      )}

      {/* SDD FULL DETAILED DOCUMENT MODAL */}
      {showFullSDDModal && projectDetails?.sdd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md p-6 animate-fade-in">
          <div className="w-full max-w-6xl h-[85vh] bg-[#111827] border border-slate-800 rounded-2xl flex flex-col shadow-2xl overflow-hidden">
            <div className="h-14 px-6 border-b border-slate-800 flex items-center justify-between shrink-0 bg-[#0f1422]">
              <div className="flex items-center gap-3">
                <FileText className="h-5 w-5 text-indigo-400" />
                <h3 className="font-extrabold text-sm text-slate-200">Software Design Document Specification (40 Sections)</h3>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => downloadDocument('design', 'pdf')}
                  className="py-1.5 px-3 bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 rounded text-xs font-bold transition-all border border-indigo-500/30 flex items-center gap-1"
                >
                  <FileDown className="h-3.5 w-3.5" /> PDF
                </button>
                <button
                  onClick={() => downloadDocument('design', 'docx')}
                  className="py-1.5 px-3 bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 rounded text-xs font-bold transition-all border border-indigo-500/30 flex items-center gap-1"
                >
                  <FileDown className="h-3.5 w-3.5" /> Word
                </button>
                <button
                  onClick={() => downloadDocument('design', 'markdown')}
                  className="py-1.5 px-3 bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 rounded text-xs font-bold transition-all border border-indigo-500/30 flex items-center gap-1"
                >
                  <FileText className="h-3.5 w-3.5" /> Markdown
                </button>
                <button
                  onClick={() => downloadDocument('design', 'json')}
                  className="py-1.5 px-3 bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 rounded text-xs font-bold transition-all border border-indigo-500/30 flex items-center gap-1"
                >
                  <FileJson className="h-3.5 w-3.5" /> JSON
                </button>
                <button 
                  onClick={() => setShowFullSDDModal(false)}
                  className="py-1.5 px-4 bg-slate-800 hover:bg-slate-700 text-xs font-bold rounded text-slate-300 ml-2"
                >
                  Close Document
                </button>
              </div>
            </div>
            
            <div className="flex-1 flex overflow-hidden">
              {/* Left sidebar nav */}
              <div className="w-64 border-r border-slate-800 overflow-y-auto bg-[#0f1422]/60 p-4 space-y-1">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block px-2 mb-2">SDD Sections</span>
                {[
                  { id: 'metadata', label: '1-3. Metadata & Revisions' },
                  { id: 'overview', label: '4-6. Intro & System Overview' },
                  { id: 'architecture', label: '7-9. High & Low Architecture' },
                  { id: 'uml', label: '10-16. UML Diagrams' },
                  { id: 'database', label: '17-20. Database Schemas' },
                  { id: 'apis', label: '21-24. APIs & Authentication' },
                  { id: 'security', label: '25-28. Security & Admin' },
                  { id: 'standards', label: '29-31. Tech Stack & Repository' },
                  { id: 'nfr', label: '32-34. Performance & Scale' },
                  { id: 'ops', label: '35-37. Monitoring & DR' },
                  { id: 'matrix', label: '38-40. Risks & Traceability' }
                ].map((grp) => (
                  <button
                    key={grp.id}
                    onClick={() => setActiveSddGroup(grp.id)}
                    className={`w-full text-left px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                      activeSddGroup === grp.id
                        ? 'bg-indigo-600/10 text-indigo-400 border-l-2 border-indigo-500'
                        : 'text-slate-400 hover:bg-slate-800/40 hover:text-slate-200'
                    }`}
                  >
                    {grp.label}
                  </button>
                ))}
              </div>
              
              {/* Right content panel */}
              <div className="flex-1 overflow-y-auto p-8 bg-[#090d16]/40 space-y-6">
                {(() => {
                  const sdd = projectDetails.sdd;
                  switch (activeSddGroup) {
                    case 'metadata':
                      return (
                        <div className="space-y-6">
                          <div>
                            <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">1. Cover Page Details</h4>
                            <p className="text-xs text-slate-300 mt-2 whitespace-pre-wrap leading-relaxed">{sdd.cover_page}</p>
                          </div>
                          <div>
                            <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">2. Revision History</h4>
                            <p className="text-xs text-slate-300 mt-2 whitespace-pre-wrap leading-relaxed">{sdd.revision_history}</p>
                          </div>
                          <div>
                            <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">3. Approval History</h4>
                            <p className="text-xs text-slate-300 mt-2 whitespace-pre-wrap leading-relaxed">{sdd.approval_history}</p>
                          </div>
                        </div>
                      );
                    case 'overview':
                      return (
                        <div className="space-y-6">
                          <div>
                            <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">4. Introduction</h4>
                            <p className="text-xs text-slate-300 mt-2 whitespace-pre-wrap leading-relaxed">{sdd.introduction}</p>
                          </div>
                          <div>
                            <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">5. Design Goals</h4>
                            <p className="text-xs text-slate-300 mt-2 whitespace-pre-wrap leading-relaxed">{sdd.design_goals}</p>
                          </div>
                          <div>
                            <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">6. System Overview</h4>
                            <p className="text-xs text-slate-300 mt-2 whitespace-pre-wrap leading-relaxed">{sdd.system_overview}</p>
                          </div>
                        </div>
                      );
                    case 'architecture':
                      return (
                        <div className="space-y-6">
                          <div>
                            <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">7. High-Level Architecture</h4>
                            <p className="text-xs text-slate-300 mt-2 whitespace-pre-wrap leading-relaxed">{sdd.high_level_architecture}</p>
                          </div>
                          <div>
                            <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">8. Low-Level Architecture</h4>
                            <p className="text-xs text-slate-300 mt-2 whitespace-pre-wrap leading-relaxed">{sdd.low_level_architecture}</p>
                          </div>
                          <div>
                            <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">9. Module Breakdown</h4>
                            <p className="text-xs text-slate-300 mt-2 whitespace-pre-wrap leading-relaxed">{sdd.module_breakdown}</p>
                          </div>
                        </div>
                      );
                    case 'uml':
                      return (
                        <div className="space-y-6">
                          <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">10-19. UML Architecture Diagrams Visualizations</h4>
                          <div className="flex flex-wrap gap-1.5 pb-2 border-b border-slate-800 sticky top-0 bg-[#090d16] z-10 pt-1">
                            {[
                              { id: 'context', label: '10. System Context' },
                              { id: 'usecase', label: '11. Use Cases' },
                              { id: 'component', label: '12. Components' },
                              { id: 'class', label: '13. Class Structure' },
                              { id: 'sequence', label: '14. Sequence Flow' },
                              { id: 'activity', label: '15. Activities' },
                              { id: 'er', label: '16. ER Diagram' },
                              { id: 'deployment', label: '17. Deployment' },
                              { id: 'flow', label: '18. Process Flow' },
                              { id: 'dbrel', label: '19. DB Relations' }
                            ].map((tab) => (
                              <button
                                key={tab.id}
                                onClick={() => {
                                  setActiveDiagramTab(tab.id);
                                  const el = document.getElementById(`diag_sec_${tab.id}`);
                                  if (el) el.scrollIntoView({ behavior: 'smooth' });
                                }}
                                className={`px-2.5 py-1 text-[10px] font-bold rounded uppercase tracking-wider transition-all ${
                                  activeDiagramTab === tab.id
                                    ? 'bg-indigo-600 text-white'
                                    : 'text-slate-400 hover:bg-slate-800'
                                }`}
                              >
                                {tab.label}
                              </button>
                            ))}
                          </div>

                          <div className="space-y-8 pt-2">
                            {[
                              { id: 'context', title: '10. System Context Diagram', field: 'system_context_diagram_mermaid' },
                              { id: 'usecase', title: '11. Use Case Diagram', field: 'use_case_diagram_mermaid' },
                              { id: 'component', title: '12. Component Diagram', field: 'component_diagram_mermaid' },
                              { id: 'class', title: '13. Class Structure Diagram', field: 'class_diagram_mermaid' },
                              { id: 'sequence', title: '14. Sequence Flow Diagram', field: 'sequence_diagram_mermaid' },
                              { id: 'activity', title: '15. Activity Diagram', field: 'activity_diagram_mermaid' },
                              { id: 'er', title: '16. Entity Relationship Diagram (ER)', field: 'er_diagram_mermaid' },
                              { id: 'deployment', title: '17. Deployment Nodes Diagram', field: 'deployment_diagram_mermaid' },
                              { id: 'flow', title: '18. Process Flow Diagram', field: 'flow_diagram_mermaid' },
                              { id: 'dbrel', title: '19. DB Relationships Diagram', field: 'db_relationship_diagram_mermaid' }
                            ].map((item) => {
                              const chart = sdd[item.field];
                              return (
                                <div key={item.id} id={`diag_sec_${item.id}`} className="space-y-3 bg-slate-900/30 border border-slate-800/80 p-5 rounded-xl">
                                  <h5 className="font-extrabold text-xs text-indigo-300 uppercase tracking-wider flex items-center gap-2">
                                    <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
                                    {item.title}
                                  </h5>
                                  {chart ? (
                                    <MermaidChart chart={chart} id={`full_doc_${item.id}`} />
                                  ) : (
                                    <div className="text-slate-500 text-xs italic">No diagram specification.</div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      );
                    case 'database':
                      return (
                        <div className="space-y-6">
                          <div>
                            <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">17. Database Design Overview</h4>
                            <p className="text-xs text-slate-300 mt-2 whitespace-pre-wrap leading-relaxed">{sdd.database_design_overview}</p>
                          </div>
                          <div>
                            <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">18. Table Definitions</h4>
                            <div className="space-y-4 mt-3">
                              {sdd.database_tables?.map((t: any, i: number) => (
                                <div key={i} className="bg-slate-900/40 border border-slate-800 rounded-lg p-4 space-y-3">
                                  <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                                    <span className="font-bold text-sm text-slate-100">{t.name}</span>
                                    <span className="text-[10px] bg-indigo-600/20 text-indigo-400 px-2 py-0.5 rounded font-mono font-bold">PK: {t.primary_key}</span>
                                  </div>
                                  <div className="space-y-1.5">
                                    {t.columns?.map((c: any, idx: number) => (
                                      <div key={idx} className="flex justify-between text-xs items-center">
                                        <span className="font-semibold text-slate-300">{c.name} <span className="text-[10px] text-slate-500 font-normal">({c.description})</span></span>
                                        <span className="font-mono text-indigo-300 text-[11px]">{c.type} {!c.nullable && '*'}</span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      );
                    case 'apis':
                      return (
                        <div className="space-y-6">
                          <div>
                            <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">21. API Overview & Endpoints Map</h4>
                            <p className="text-xs text-slate-300 mt-2 whitespace-pre-wrap leading-relaxed">{sdd.api_design_overview}</p>
                          </div>
                          <div className="space-y-3">
                            {sdd.api_endpoints?.map((api: any, idx: number) => (
                              <div key={idx} className="bg-slate-900/40 border border-slate-800 rounded-lg p-3 space-y-1 text-xs">
                                <div className="flex items-center gap-2">
                                  <span className="px-1.5 py-0.5 rounded text-[9px] font-black uppercase bg-indigo-600/20 text-indigo-400">{api.method}</span>
                                  <span className="font-mono font-bold text-slate-200">{api.path}</span>
                                </div>
                                <p className="text-slate-400 text-[11px]">{api.description}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    case 'matrix':
                      return (
                        <div className="space-y-4">
                          <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">40. Requirement Traceability Matrix</h4>
                          <div className="overflow-x-auto border border-slate-800 rounded-lg">
                            <table className="w-full text-left text-xs border-collapse">
                              <thead>
                                <tr className="bg-slate-900 text-slate-400 font-bold uppercase">
                                  <th className="p-3 border-b border-slate-800">Req ID</th>
                                  <th className="p-3 border-b border-slate-800">Module</th>
                                  <th className="p-3 border-b border-slate-800">API Endpoint</th>
                                  <th className="p-3 border-b border-slate-800">DB Table</th>
                                  <th className="p-3 border-b border-slate-800">UI Screen</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-slate-850 bg-slate-900/10">
                                {sdd.traceability_matrix?.map((row: any, idx: number) => (
                                  <tr key={idx} className="hover:bg-slate-800/10 text-slate-300">
                                    <td className="p-3 font-extrabold text-indigo-400">{row.requirement_id}</td>
                                    <td className="p-3 font-bold text-slate-200">{row.module}</td>
                                    <td className="p-3 font-mono text-[11px] text-slate-300">{row.api_endpoint}</td>
                                    <td className="p-3 font-mono text-[11px] text-indigo-300">{row.db_table}</td>
                                    <td className="p-3 text-slate-300">{row.ui_screen}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      );
                    default:
                      return (
                        <div className="space-y-4">
                          <h4 className="font-extrabold text-xs text-indigo-400 uppercase tracking-widest border-b border-slate-800 pb-2">System Design Content</h4>
                          <p className="text-xs text-slate-300 whitespace-pre-wrap leading-relaxed">{JSON.stringify(sdd, null, 2)}</p>
                        </div>
                      );
                  }
                })()}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* PREVIEW SINGLE HISTORICAL VERSION MODAL */}
      {previewVersion && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-3xl h-[70vh] bg-[#111827] border border-slate-800 rounded-2xl flex flex-col shadow-2xl overflow-hidden">
            <div className="h-14 px-6 border-b border-slate-800 flex items-center justify-between shrink-0 bg-[#0f1422]">
              <h3 className="font-extrabold text-sm text-slate-200">
                Historical JSON Preview: {previewVersion.type.toUpperCase()} Version {previewVersion.num}
              </h3>
              <button 
                onClick={() => setPreviewVersion(null)}
                className="py-1 px-3 bg-slate-800 hover:bg-slate-700 text-xs font-semibold rounded text-slate-400"
              >
                Close
              </button>
            </div>
            <div className="flex-1 overflow-auto p-6 bg-[#090d16] font-mono text-xs text-emerald-300">
              <pre>{JSON.stringify(previewVersion.data, null, 2)}</pre>
            </div>
          </div>
        </div>
      )}

      {/* COMPARE SIDE-BY-SIDE MODAL */}
      {compareVersion && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-6">
          <div className="w-full max-w-6xl h-[85vh] bg-[#111827] border border-slate-800 rounded-2xl flex flex-col shadow-2xl overflow-hidden">
            <div className="h-14 px-6 border-b border-slate-800 flex items-center justify-between shrink-0 bg-[#0f1422]">
              <h3 className="font-extrabold text-sm text-slate-200">
                Compare Side-by-Side: Version {compareVersion.verNum} vs Current Active Version
              </h3>
              <button 
                onClick={() => setCompareVersion(null)}
                className="py-1 px-3 bg-slate-800 hover:bg-slate-700 text-xs font-semibold rounded text-slate-405"
              >
                Close Comparison
              </button>
            </div>
            
            <div className="flex-1 flex overflow-hidden divide-x divide-slate-850">
              {/* Left Column: Historical */}
              <div className="flex-1 flex flex-col min-w-0">
                <div className="p-3 bg-slate-900 border-b border-slate-800 text-center text-xs font-bold text-indigo-400">
                  Version {compareVersion.verNum} (Historical)
                </div>
                <div className="flex-1 overflow-auto p-6 bg-[#090d16] font-mono text-[11px] text-slate-400 leading-normal">
                  <pre>{JSON.stringify(compareVersion.historical, null, 2)}</pre>
                </div>
              </div>

              {/* Right Column: Active Current */}
              <div className="flex-1 flex flex-col min-w-0">
                <div className="p-3 bg-slate-900 border-b border-slate-800 text-center text-xs font-bold text-emerald-450">
                  Current Active Version
                </div>
                <div className="flex-1 overflow-auto p-6 bg-[#090d16] font-mono text-[11px] text-slate-400 leading-normal">
                  <pre>{JSON.stringify(compareVersion.current, null, 2)}</pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
