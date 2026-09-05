import React, { useState, useEffect } from 'react';
import { 
  Code, 
  Database, 
  FileDown, 
  Layers, 
  ShieldCheck, 
  CheckCircle2, 
  AlertCircle, 
  RefreshCw, 
  Clock, 
  Terminal, 
  ChevronRight,
  Sparkles,
  Lock,
  History,
  FileJson,
  Activity,
  User,
  ArrowRight,
  CheckSquare,
  Square
} from 'lucide-react';
import { api, API_BASE, apiFetch, API_KEY } from '../services/api';

interface DevelopmentPanelProps {
  projectId: string;
  projectDetails: any;
  fetchProjectDetails: (id: string) => Promise<void>;
  setToastMessage: (msg: string | null) => void;
}

export const DevelopmentPanel: React.FC<DevelopmentPanelProps> = ({
  projectId,
  projectDetails,
  fetchProjectDetails,
  setToastMessage
}) => {
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [selectedReport, setSelectedReport] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [submittingReview, setSubmittingReview] = useState(false);

  // Gated reviews controls
  const [reviewerName, setReviewerName] = useState('Lead Developer');
  const [reviewComments, setReviewComments] = useState('');
  const [rejectedModules, setRejectedModules] = useState<string[]>([]);
  
  const [devData, setDevData] = useState<any>(null);
  const [tasks, setTasks] = useState<any[]>([]);
  const [agents, setAgents] = useState<any[]>([]);
  const [artifacts, setArtifacts] = useState<any[]>([]);

  const fetchDevStatus = async () => {
    setLoading(true);
    try {
      // 1. Fetch main state details
      const res = await apiFetch(`${API_BASE}/projects/${projectId}/development`);
      if (res.ok) {
        const data = await res.json();
        setDevData(data);
        if (data.state?.manifest?.length > 0 && !selectedFile && !selectedReport) {
          setSelectedFile(data.state.manifest[0].path);
        }
        if (data.state?.failing_modules?.length > 0 && rejectedModules.length === 0) {
          setRejectedModules(data.state.failing_modules);
        }
      }
      
      // 2. Fetch tasks list
      const tasksRes = await apiFetch(`${API_BASE}/projects/${projectId}/development/tasks`);
      if (tasksRes.ok) {
        const tData = await tasksRes.json();
        setTasks(tData.tasks || []);
      }

      // 3. Fetch agent statuses
      const agentsRes = await apiFetch(`${API_BASE}/projects/${projectId}/development/agents`);
      if (agentsRes.ok) {
        const aData = await agentsRes.json();
        setAgents(aData.agents || []);
      }

      // 4. Fetch compiled database artifacts list
      const artifactsRes = await apiFetch(`${API_BASE}/projects/${projectId}/development/artifacts`);
      if (artifactsRes.ok) {
        const artData = await artifactsRes.json();
        setArtifacts(artData.artifacts || []);
      }
    } catch (err) {
      console.error("Error loading development data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (projectId) {
      fetchDevStatus();
    }
  }, [projectId, projectDetails?.project?.current_phase]);

  const handleGenerateCode = async () => {
    setGenerating(true);
    try {
      const res = await apiFetch(`${API_BASE}/projects/${projectId}/development/start`, {
        method: 'POST'
      });
      if (res.ok) {
        setToastMessage("Multi-agent parallel code generation loop initiated successfully.");
        await fetchDevStatus();
        await fetchProjectDetails(projectId);
      } else {
        const err = await res.json();
        alert(`Generation failed: ${err.detail || 'Internal error'}`);
      }
    } catch (err) {
      console.error(err);
      alert("Error starting multi-agent loop.");
    } finally {
      setGenerating(false);
    }
  };

  const handleReview = async (status: 'APPROVED' | 'REJECTED') => {
    if (status === 'REJECTED' && !reviewComments.trim()) {
      alert("Please provide review comments detailing the revisions required.");
      return;
    }
    setSubmittingReview(true);
    try {
      const res = await apiFetch(`${API_BASE}/projects/${projectId}/development/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          status,
          comments: reviewComments,
          reviewer_name: reviewerName,
          rejected_modules: rejectedModules
        })
      });
      
      if (res.ok) {
        setToastMessage(
          status === 'APPROVED' 
            ? "Development phase approved. Project is READY FOR TESTING." 
            : `Review submitted. Re-invoking affected agent(s): ${rejectedModules.join(', ')}`
        );
        setReviewComments('');
        setRejectedModules([]);
        await fetchDevStatus();
        await fetchProjectDetails(projectId);
      } else {
        const err = await res.json();
        alert(`Gated review failed: ${err.detail}`);
      }
    } catch (err) {
      console.error(err);
      alert("Error submitting review decision.");
    } finally {
      setSubmittingReview(false);
    }
  };

  const toggleRejectedModule = (mod: string) => {
    if (rejectedModules.includes(mod)) {
      setRejectedModules(rejectedModules.filter(m => m !== mod));
    } else {
      setRejectedModules([...rejectedModules, mod]);
    }
  };

  const downloadArtifact = (type: string) => {
    window.open(`${API_BASE}/projects/${projectId}/development/artifacts/download?type=${type}&api_key=${API_KEY}`, '_blank');
  };

  if (!devData) {
    return (
      <div className="flex-grow flex items-center justify-center bg-[#0b0f19]">
        <RefreshCw className="h-8 w-8 text-indigo-500 animate-spin" />
      </div>
    );
  }

  const { state } = devData;
  const manifest = state?.manifest || [];
  const files = state?.generated_files || {};
  const phase = state?.phase || 'DESIGN_APPROVED';
  const validationErrors = state?.validation_errors || [];
  const logs = state?.logs || [];
  const executionLogs = state?.execution_logs || [];
  const reports = state?.reports || {};
  const selfReviewReport = state?.self_review_report || {};
  
  const buildStatus = state?.build_status || 'PENDING';
  const progressPercentage = state?.progress_percentage || 0;
  const currentVersion = state?.current_version || 1;
  const qualityScore = state?.quality_score || 0.0;
  const securityScore = state?.security_score || 0.0;

  // Map agent status dynamically from tasks list or orchestrator state status maps
  const getAgentStatus = (agentName: string): string => {
    if (state?.agent_statuses && state.agent_statuses[agentName]) {
      return state.agent_statuses[agentName];
    }
    const task = tasks.find(t => t.owner_agent === agentName);
    if (task) return task.status;
    return "PENDING";
  };

  const getAgentStatusBadge = (status: string) => {
    switch (status) {
      case "COMPLETED":
        return <span className="text-[10px] font-black uppercase text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">Completed</span>;
      case "RUNNING":
        return <span className="text-[10px] font-black uppercase text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20 animate-pulse">Running</span>;
      case "FAILED":
        return <span className="text-[10px] font-black uppercase text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded border border-rose-500/20 animate-pulse">Failed</span>;
      case "REVISION_REQUIRED":
        return <span className="text-[10px] font-black uppercase text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20 animate-pulse">Revision Required</span>;
      default:
        return <span className="text-[10px] font-black uppercase text-slate-500 bg-slate-900 border border-slate-800 px-2 py-0.5 rounded">Pending</span>;
    }
  };

  const getAgentDetails = (agentName: string) => {
    const log = executionLogs.find((l: any) => l.agent_name === agentName);
    return log || {};
  };

  return (
    <div className="flex-1 flex overflow-hidden bg-[#0f1422]">
      
      {/* LEFT: Code Tree and Verification Reports */}
      <div className="w-80 border-r border-slate-800 bg-[#111827] flex flex-col justify-between shrink-0 overflow-y-auto">
        <div className="space-y-6 pb-6">
          
          <div className="h-14 border-b border-slate-800 flex items-center justify-between px-6 bg-[#0f1422] shrink-0">
            <div className="flex items-center gap-2">
              <Terminal className="h-4.5 w-4.5 text-indigo-400" />
              <span className="text-xs font-extrabold uppercase tracking-wider text-slate-350">Code Workspace</span>
            </div>
            <span className="text-[10px] bg-slate-900 border border-slate-800 px-2 py-0.5 rounded font-black text-slate-400">
              V{currentVersion}
            </span>
          </div>

          {/* Project Traceability Link Info */}
          {projectDetails && (
            <div className="px-6 space-y-1">
              <span className="text-[9px] font-bold text-slate-500 uppercase tracking-widest block">SDLC Scope target</span>
              <h4 className="text-xs font-bold text-slate-300">{projectDetails.project.name}</h4>
              <p className="text-[10px] text-slate-500 leading-relaxed line-clamp-2">{projectDetails.project.description}</p>
            </div>
          )}

          {/* Code Files List */}
          <div className="space-y-2">
            <div className="px-6 flex items-center justify-between text-[10px] font-bold text-indigo-400 uppercase tracking-wider">
              <span>Planned Source Code</span>
              <span>{manifest.length} Files</span>
            </div>
            <div className="px-4 space-y-1.5">
              {manifest.length === 0 ? (
                <div className="py-4 text-center text-xs text-slate-500 italic">
                  Scaffolds not generated.
                </div>
              ) : (
                manifest.map((file: any) => {
                  const isSelected = selectedFile === file.path;
                  return (
                    <button
                      key={file.path}
                      onClick={() => {
                        setSelectedFile(file.path);
                        setSelectedReport(null);
                      }}
                      className={`w-full text-left p-3 rounded-xl border transition-all flex flex-col gap-1.5 ${
                        isSelected
                          ? 'bg-indigo-650/15 border-indigo-500 text-indigo-200 shadow-md' 
                          : 'bg-slate-900/50 border-slate-800/80 hover:border-slate-700 text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      <div className="flex items-center justify-between w-full">
                        <span className="font-mono text-xs font-bold truncate">{file.path}</span>
                        {file.security_sensitive && (
                          <span className="flex items-center gap-0.5 text-[8px] font-extrabold text-amber-500 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">
                            <ShieldCheck className="h-2.5 w-2.5" />
                            Shield
                          </span>
                        )}
                      </div>
                      <div className="flex items-center justify-between text-[9px] text-slate-500 w-full font-semibold">
                        <span>{file.owner_agent}</span>
                        <span className="uppercase text-[8px] tracking-wider text-indigo-500/80">{file.module}</span>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>

          {/* Diagnostic Reports Viewer list */}
          {Object.keys(reports).length > 0 && (
            <div className="space-y-2">
              <div className="px-6 text-[10px] font-bold text-indigo-400 uppercase tracking-wider block">
                Verification Artifacts
              </div>
              <div className="px-4 space-y-1">
                {Object.keys(reports).map((key) => {
                  const isSelected = selectedReport === key;
                  return (
                    <button
                      key={key}
                      onClick={() => {
                        setSelectedReport(key);
                        setSelectedFile(null);
                      }}
                      className={`w-full text-left px-3.5 py-2.5 rounded-lg border transition-all flex items-center justify-between ${
                        isSelected
                          ? 'bg-emerald-650/15 border-emerald-500 text-emerald-300'
                          : 'bg-slate-900/50 border-slate-800/80 hover:border-slate-700 text-slate-400'
                      }`}
                    >
                      <span className="text-xs font-semibold">{getReportName(key)}</span>
                      <ChevronRight className="h-3.5 w-3.5 text-slate-600 shrink-0" />
                    </button>
                  );
                })}
              </div>
            </div>
          )}

        </div>

        {/* Artifacts Download Checklist */}
        {artifacts.length > 0 && (
          <div className="p-4 border-t border-slate-800 bg-[#0c0f16]/60 shrink-0 space-y-2">
            <span className="text-[9px] font-bold text-slate-500 uppercase tracking-widest block">Available Artifacts</span>
            <div className="space-y-1.5">
              {artifacts.map((art: any) => (
                <button
                  key={art.id}
                  onClick={() => downloadArtifact(art.artifact_type)}
                  className="w-full flex items-center justify-between py-1.5 px-3 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-[10px] text-slate-400 font-bold tracking-wide transition-all"
                >
                  <span className="truncate">{art.artifact_type.replace('_', ' ')}</span>
                  <FileDown className="h-3.5 w-3.5 text-indigo-400 shrink-0" />
                </button>
              ))}
            </div>
          </div>
        )}

      </div>

      {/* CENTER: Editor Panel & Parallel Worker Status Cards */}
      <div className="flex-1 flex flex-col min-w-0 bg-[#0b0f19]">
        
        <div className="h-14 border-b border-slate-800 flex items-center justify-between px-8 bg-[#111827] shrink-0">
          <div className="flex items-center gap-3">
            <span className="text-xs font-extrabold uppercase tracking-wider py-1.5 px-3 rounded-lg border bg-indigo-650/20 border-indigo-500 text-indigo-300">
              Code Workspace & Artifacts
            </span>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Build Status:</span>
            <span className={`text-[10px] font-black uppercase px-2.5 py-0.5 rounded border ${
              buildStatus === 'SUCCESS' ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' : 'bg-rose-500/10 border-rose-500/20 text-rose-400'
            }`}>{buildStatus}</span>
          </div>
        </div>

        {/* Content View */}
        <div className="flex-1 p-8 overflow-y-auto space-y-6">
          {state?.execution_state && state.execution_state !== 'FAILED' && state.execution_state !== 'COMPLETED' && (
            <div className="bg-rose-500/10 border border-rose-500/30 p-5 rounded-2xl space-y-2">
              <div className="flex items-center gap-2 text-rose-450 font-black text-xs uppercase tracking-wider">
                <AlertCircle className="h-4.5 w-4.5 text-rose-500" />
                Error Code Detected: {state.execution_state}
              </div>
              <p className="text-xs text-rose-300 leading-normal font-medium">{state.error_message}</p>
            </div>
          )}

          {/* Handoff Banner when Development is Approved & Ready for Testing */}
          {phase === 'READY_FOR_TESTING' && (
            <div className="bg-gradient-to-r from-indigo-950/60 via-cyan-950/30 to-slate-900 border border-cyan-500/30 p-5 rounded-2xl space-y-3 shadow-xl">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-xl bg-cyan-500/15 border border-cyan-500/30 text-cyan-400 flex items-center justify-center font-bold">
                    <ShieldCheck className="h-5 w-5" />
                  </div>
                  <div>
                    <h4 className="text-sm font-black text-slate-100 uppercase tracking-wide">
                      Development Stage Complete & Approved &mdash; Ready for Testing
                    </h4>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Source code manifests, architectural interfaces, and build artifacts are certified. Proceed to the 8-Phase Testing Agent.
                    </p>
                  </div>
                </div>
                <span className="px-3 py-1 rounded-full text-xs font-black bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                  READY FOR TESTING
                </span>
              </div>
              <div className="flex items-center justify-between pt-2 border-t border-slate-800/80 text-xs">
                <span className="text-slate-400">
                  All test design, multi-runner execution, risk telemetry, and release governance are handled by the <strong className="text-cyan-300">8-Phase Testing Agent</strong>.
                </span>
              </div>
            </div>
          )}
          
          {/* Parallel Worker Status Cards (6 Core Development Agents) */}
          {manifest.length > 0 && (
            <div className="space-y-2">
              <span className="text-[10px] font-extrabold uppercase tracking-widest text-slate-500">
                Multi-Agent Parallel Development Workers
              </span>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2.5">
                {[
                  { name: "DatabaseDeveloperAgent", label: "Database Agent", icon: <Database className="h-3.5 w-3.5" /> },
                  { name: "BackendDeveloperAgent", label: "Backend Agent", icon: <Code className="h-3.5 w-3.5" /> },
                  { name: "FrontendDeveloperAgent", label: "Frontend Agent", icon: <Layers className="h-3.5 w-3.5" /> },
                  { name: "APIIntegrationAgent", label: "API Integration", icon: <Activity className="h-3.5 w-3.5" /> },
                  { name: "DocumentationAgent", label: "Documentation", icon: <FileJson className="h-3.5 w-3.5" /> },
                  { name: "SelfReviewAgent", label: "Self Review", icon: <ShieldCheck className="h-3.5 w-3.5" /> }
                ].map((ag) => {
                  const status = getAgentStatus(ag.name);
                  const details = getAgentDetails(ag.name);
                  const agentErrors = validationErrors.filter((e: any) => e.agent === ag.name);
                  return (
                    <div key={ag.name} className="bg-slate-900 border border-slate-800 p-2.5 rounded-xl flex flex-col justify-between gap-2 min-h-[100px] shadow-sm">
                      <div className="flex items-center gap-1.5 text-xs font-bold text-slate-350">
                        {ag.icon}
                        <span className="truncate text-[11px]">{ag.label}</span>
                      </div>
                      <div className="text-[9px] text-slate-500 space-y-0.5 font-semibold">
                        {details.duration !== undefined && (
                          <div>Duration: <span className="text-slate-300">{details.duration.toFixed(1)}s</span></div>
                        )}
                        {agentErrors.length > 0 && (
                          <div className="text-rose-400 font-bold">Errors: {agentErrors.length}</div>
                        )}
                      </div>
                      <div className="flex items-center justify-between w-full">
                        {getAgentStatusBadge(status)}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Stepper Progress bar */}
          {manifest.length > 0 && (
            <div className="bg-slate-900 border border-slate-850 p-4 rounded-2xl space-y-2">
              <div className="flex items-center justify-between text-xs font-bold">
                <span className="text-slate-400">Pipeline execution state</span>
                <span className="text-indigo-400">{progressPercentage}%</span>
              </div>
              <div className="w-full bg-slate-950 h-1.5 rounded-full overflow-hidden border border-slate-800">
                <div className="bg-indigo-500 h-full rounded-full transition-all duration-500" style={{ width: `${progressPercentage}%` }}></div>
              </div>
              <span className="text-[10px] text-slate-500 block font-mono">Stage: {state.current_agent || 'Orchestrator'} | {state.current_task || 'Idle'}</span>
            </div>
          )}

          {/* Advisory self review metrics card */}
          {Object.keys(selfReviewReport).length > 0 && (
            <div className="bg-[#121625]/60 border border-slate-800 p-5 rounded-2xl space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <h4 className="text-xs font-extrabold uppercase tracking-widest text-indigo-400 flex items-center gap-2">
                  <Sparkles className="h-4 w-4" />
                  Stage 6: AI Self-Review report (Advisory)
                </h4>
                <div className="flex gap-4 text-xs font-bold text-slate-400">
                  <div>Quality Score: <span className="text-emerald-400">{qualityScore.toFixed(1)}/10</span></div>
                  <div>Security Score: <span className="text-emerald-400">{securityScore.toFixed(1)}/10</span></div>
                </div>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <span className="text-[10px] font-bold text-slate-500 uppercase block">Strengths</span>
                  <ul className="text-xs text-slate-300 list-disc list-inside space-y-0.5">
                    {selfReviewReport.strengths?.map((s: string, i: number) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                </div>
                <div className="space-y-1">
                  <span className="text-[10px] font-bold text-slate-500 uppercase block">Recommended Improvements</span>
                  <ul className="text-xs text-slate-300 list-disc list-inside space-y-0.5">
                    {selfReviewReport.improvements?.map((s: string, i: number) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* Source/Report File Pre Container */}
          {selectedFile && files[selectedFile] ? (
            <pre className="bg-slate-950 p-6 rounded-2xl border border-slate-800 text-xs font-mono text-indigo-300 overflow-auto h-[55vh] leading-relaxed select-text shadow-inner">
              <code>{files[selectedFile]}</code>
            </pre>
          ) : selectedReport && reports[selectedReport] ? (
            <pre className="bg-slate-950 p-6 rounded-2xl border border-slate-800 text-xs font-mono text-emerald-300 overflow-auto h-[55vh] leading-relaxed select-text shadow-inner">
              <code>{reports[selectedReport]}</code>
            </pre>
          ) : (
            <div className="h-[45vh] flex flex-col items-center justify-center text-slate-500 space-y-4">
              <div className="h-16 w-16 bg-slate-900 border border-slate-800 rounded-full flex items-center justify-center text-indigo-500">
                <Code className="h-8 w-8" />
              </div>
              <div className="text-center max-w-sm space-y-2">
                <h4 className="font-bold text-slate-300">Code Workspace Empty</h4>
                <p className="text-xs text-slate-400">
                  {phase === 'DESIGN_APPROVED' || phase === 'planning'
                    ? "Initialize the multi-agent orchestrator to generate files scaffolds."
                    : "No source contents available for preview."}
                </p>
                
                {(phase === 'DESIGN_APPROVED' || phase === 'planning') && (
                  <button
                    onClick={handleGenerateCode}
                    disabled={generating}
                    className="mt-4 flex items-center gap-2 py-2 px-5 bg-indigo-650 hover:bg-indigo-600 text-white font-extrabold rounded-lg text-xs uppercase tracking-wider transition-all disabled:opacity-50 mx-auto"
                  >
                    {generating && <RefreshCw className="h-3.5 w-3.5 animate-spin" />}
                    Initialize Multi-Agent Scaffold
                  </button>
                )}
              </div>
            </div>
          )}

        </div>
      </div>

      {/* RIGHT: Workflow Pipeline Stepper, human reviews gate, execution logs */}
      <div className="w-80 border-l border-slate-800 bg-[#111827] flex flex-col shrink-0 overflow-y-auto">
        
        {/* Pipeline Stepper */}
        <div className="p-5 border-b border-slate-800 bg-[#0f1422]">
          <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block mb-4">Development Stepper</h4>
          <div className="space-y-4">
            {[
              { id: 'DEVELOPMENT_PLANNING', label: '1-3. Context & Planning', activePhases: ['DEVELOPMENT_PLANNING', 'DESIGN_APPROVED'] },
              { id: 'GENERATING_CODE', label: '4. Parallel Code Generation', activePhases: ['GENERATING_CODE'] },
              { id: 'VALIDATING', label: '5. Merge & Validation', activePhases: ['VALIDATING'] },
              { id: 'AI_SELF_REVIEW', label: '6. AI Self-Review', activePhases: ['AI_SELF_REVIEW'] },
              { id: 'DOCUMENT_REFINEMENT', label: '7. Documentation Refinement', activePhases: ['DOCUMENT_REFINEMENT'] },
              { id: 'ARTIFACT_GENERATION', label: '8. Artifacts Generator', activePhases: ['ARTIFACT_GENERATION'] },
              { id: 'WAITING_FOR_REVIEW', label: '9. Gated Human Review', activePhases: ['WAITING_FOR_REVIEW', 'ERROR'] },
              { id: 'READY_FOR_TESTING', label: '10. Ready for Testing Stage', activePhases: ['READY_FOR_TESTING'] }
            ].map((s) => {
              const isActive = s.activePhases.includes(phase);
              const isDone = 
                (s.id === 'DEVELOPMENT_PLANNING' && phase !== 'DEVELOPMENT_PLANNING' && phase !== 'DESIGN_APPROVED') ||
                (s.id === 'GENERATING_CODE' && phase !== 'DEVELOPMENT_PLANNING' && phase !== 'DESIGN_APPROVED' && phase !== 'GENERATING_CODE') ||
                (s.id === 'VALIDATING' && phase !== 'DEVELOPMENT_PLANNING' && phase !== 'DESIGN_APPROVED' && phase !== 'GENERATING_CODE' && phase !== 'VALIDATING') ||
                (s.id === 'AI_SELF_REVIEW' && phase !== 'DEVELOPMENT_PLANNING' && phase !== 'DESIGN_APPROVED' && phase !== 'GENERATING_CODE' && phase !== 'VALIDATING' && phase !== 'AI_SELF_REVIEW') ||
                (s.id === 'DOCUMENT_REFINEMENT' && phase !== 'DEVELOPMENT_PLANNING' && phase !== 'DESIGN_APPROVED' && phase !== 'GENERATING_CODE' && phase !== 'VALIDATING' && phase !== 'AI_SELF_REVIEW' && phase !== 'DOCUMENT_REFINEMENT') ||
                (s.id === 'ARTIFACT_GENERATION' && phase !== 'DEVELOPMENT_PLANNING' && phase !== 'DESIGN_APPROVED' && phase !== 'GENERATING_CODE' && phase !== 'VALIDATING' && phase !== 'AI_SELF_REVIEW' && phase !== 'DOCUMENT_REFINEMENT' && phase !== 'ARTIFACT_GENERATION') ||
                (s.id === 'WAITING_FOR_REVIEW' && phase === 'READY_FOR_TESTING') ||
                (s.id === 'READY_FOR_TESTING' && phase === 'READY_FOR_TESTING');
              
              return (
                <div key={s.id} className="flex items-center gap-3 text-xs">
                  {isDone ? (
                    <CheckCircle2 className="h-4.5 w-4.5 text-emerald-400 shrink-0" />
                  ) : isActive ? (
                    <RefreshCw className="h-4.5 w-4.5 text-indigo-400 animate-spin shrink-0" />
                  ) : (
                    <Clock className="h-4.5 w-4.5 text-slate-700 shrink-0" />
                  )}
                  <span className={`font-semibold ${isActive ? 'text-indigo-400' : isDone ? 'text-slate-350' : 'text-slate-600'}`}>
                    {s.label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* HUMAN REVIEW FORM AND CHECKBOX MODULE SELECTION */}
        {(phase === 'WAITING_FOR_REVIEW' || phase === 'ERROR') && (
          <div className="p-5 border-b border-slate-800 bg-[#121625]/30 space-y-4">
            <div className="bg-indigo-650/15 border border-indigo-500/20 p-4 rounded-xl space-y-1">
              <h4 className="text-[10px] font-extrabold uppercase tracking-widest text-indigo-400 flex items-center gap-1.5">
                <Sparkles className="h-3.5 w-3.5" />
                Gated Human Review
              </h4>
              <p className="text-[10px] text-slate-400 leading-normal">
                {phase === 'ERROR' 
                  ? "Build check failed. You can inspect compiler error logs and click 'Reject & Revise' below."
                  : "Review codebase output and files manifest. Approve to transition to Testing Stage, or select affected modules to reject."}
              </p>
            </div>

            <div className="space-y-3.5">
              <div className="bg-slate-950/60 border border-slate-800 p-2.5 rounded-lg flex items-center justify-between text-[10px] text-slate-450 font-bold uppercase tracking-wider">
                <span>Version: <span className="text-indigo-400">V{currentVersion}</span></span>
                <span>Parent: <span className="text-slate-300 font-mono text-[9px]">{state?.parent_version_id ? `...${state.parent_version_id.substring(state.parent_version_id.length - 8)}` : 'None'}</span></span>
              </div>
              <div className="space-y-1">
                <label className="text-[9px] font-extrabold text-slate-500 uppercase tracking-wider block">Reviewer Name</label>
                <input 
                  type="text" 
                  value={reviewerName} 
                  onChange={(e) => setReviewerName(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-750 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none"
                />
              </div>

              <div className="space-y-1">
                <label className="text-[9px] font-extrabold text-slate-500 uppercase tracking-wider block">Review Comments</label>
                <textarea 
                  rows={3} 
                  placeholder="Describe your review observations..." 
                  value={reviewComments} 
                  onChange={(e) => setReviewComments(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-750 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none resize-none"
                />
              </div>

              {/* TARGETED REVISION SELECTION */}
              <div className="space-y-2 bg-slate-950 p-3 rounded-xl border border-slate-800">
                <label className="text-[9px] font-extrabold text-rose-400 uppercase tracking-wider block">Targeted Revision Selection</label>
                <span className="text-[9px] text-slate-500 block leading-tight mb-2">Check modules to regenerate on Reject.</span>
                <div className="space-y-1.5">
                  {[
                    { id: 'database', label: 'Database Agent' },
                    { id: 'backend', label: 'Backend Agent' },
                    { id: 'frontend', label: 'Frontend Agent' },
                    { id: 'documentation', label: 'Documentation Agent' }
                  ].map((m) => {
                    const isChecked = rejectedModules.includes(m.id);
                    return (
                      <button
                        key={m.id}
                        type="button"
                        onClick={() => toggleRejectedModule(m.id)}
                        className="w-full flex items-center gap-2 text-[10px] text-slate-400 hover:text-slate-250 font-bold transition-all text-left"
                      >
                        {isChecked ? (
                          <CheckSquare className="h-4 w-4 text-rose-500 shrink-0" />
                        ) : (
                          <Square className="h-4 w-4 text-slate-650 shrink-0" />
                        )}
                        <span>{m.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="flex gap-2">
                <button
                  onClick={() => handleReview('REJECTED')}
                  disabled={submittingReview}
                  className="flex-1 py-2 px-3 rounded-lg border border-rose-500/30 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 font-extrabold text-[11px] uppercase tracking-wider transition-all disabled:opacity-50"
                >
                  Reject & Revise
                </button>
                <button
                  onClick={() => handleReview('APPROVED')}
                  disabled={submittingReview || phase === 'ERROR'}
                  className="flex-1 py-2 px-3 rounded-lg bg-emerald-650 hover:bg-emerald-500 text-white font-extrabold text-[11px] uppercase tracking-wider transition-all shadow disabled:opacity-50 disabled:bg-slate-800 disabled:text-slate-500"
                >
                  Approve Code
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Node execution logs */}
        {executionLogs.length > 0 && (
          <div className="p-5 border-b border-slate-800 space-y-4">
            <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block">Node Execution Statistics</h4>
            <div className="space-y-3 max-h-56 overflow-y-auto pr-1">
              {executionLogs.map((log: any, idx: number) => (
                <div key={idx} className="bg-slate-900 border border-slate-850 p-2.5 rounded-lg text-[10px] space-y-1">
                  <div className="flex items-center justify-between font-bold">
                    <span className="text-slate-300 font-mono">{log.node_name}</span>
                    <span className={`px-1 rounded ${
                      log.status === 'SUCCESS' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
                    }`}>{log.status}</span>
                  </div>
                  <div className="grid grid-cols-2 gap-y-0.5 text-slate-500">
                    <div>Duration: <span className="text-slate-350">{log.duration?.toFixed(2)}s</span></div>
                    <div>Agent: <span className="text-slate-350">{log.agent_name || 'Orchestrator'}</span></div>
                    <div>Stage: <span className="text-slate-350">{log.stage}</span></div>
                    <div>LLM: <span className="text-slate-350">{log.llm_provider || 'gemini'}</span></div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Development logs */}
        <div className="p-5 space-y-4">
          <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block">Development Logs</h4>
          <div className="space-y-4 max-h-40 overflow-y-auto">
            {logs.length === 0 ? (
              <p className="text-xs text-slate-650 italic">No logs recorded.</p>
            ) : (
              logs.map((log: any, idx: number) => (
                <div key={idx} className="space-y-0.5 border-l border-slate-700 pl-3 text-[10px]">
                  <span className="font-bold text-slate-400 uppercase tracking-wider block">
                    {log.action.replace('_', ' ')}
                  </span>
                  <p className="text-slate-500 leading-relaxed">{log.details}</p>
                </div>
              ))
            )}
          </div>
        </div>

      </div>

    </div>
  );
};

const getReportName = (key: string) => {
  switch (key) {
    case 'manifest': return 'Manifest.json';
    case 'build_report': return 'BuildReport.json';
    case 'validation_report': return 'ValidationReport.json';
    case 'folder_structure': return 'FolderStructure.json';
    case 'metadata': return 'GenerationMetadata.json';
    case 'readme': return 'README.md';
    default: return key;
  }
};

export default DevelopmentPanel;
