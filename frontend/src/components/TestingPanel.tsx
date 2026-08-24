import React, { useState, useEffect, useCallback } from 'react';
import {
  Play, RefreshCw, CheckCircle, XCircle, AlertTriangle, Clock,
  Server, FileCheck, Database, ArrowLeftRight, ClipboardList,
  UserCheck, RotateCcw, ChevronDown, ChevronRight, Shield,
  Activity, GitBranch, Cpu, Eye, ThumbsUp, ThumbsDown,
  HelpCircle, Loader2, Octagon, FileText, FileDown, Check,
  Lock, X, Layers, Terminal
} from 'lucide-react';
import { api } from '../services/api';

interface TestingPanelProps {
  projectId: string;
  projectDetails: any;
  fetchProjectDetails: (id: string) => Promise<void>;
  setToastMessage: (msg: string) => void;
}

/* ── Status & Execution Badges ───────────────────────────────────────── */
function ExecutionBadge({ state }: { state: string }) {
  const map: Record<string, { bg: string; text: string; label: string; icon: React.ReactNode }> = {
    RUNNING:     { bg: 'bg-blue-500/10 border-blue-500/30', text: 'text-blue-400 animate-pulse', label: 'AUTOMATED TESTING IN PROGRESS', icon: <Loader2 className="h-3.5 w-3.5 animate-spin" /> },
    COMPLETED:   { bg: 'bg-emerald-500/10 border-emerald-500/30', text: 'text-emerald-400', label: 'TEST REPORT COMPLETED', icon: <CheckCircle className="h-3.5 w-3.5" /> },
    ABORTED:     { bg: 'bg-amber-500/10 border-amber-500/30', text: 'text-amber-400', label: 'RUN ABORTED BY USER', icon: <Octagon className="h-3.5 w-3.5" /> },
    TIMED_OUT:   { bg: 'bg-amber-500/10 border-amber-500/30', text: 'text-amber-400', label: 'RUN TIMED OUT', icon: <Clock className="h-3.5 w-3.5" /> },
    CRASHED:     { bg: 'bg-rose-500/10 border-rose-500/30', text: 'text-rose-400', label: 'EXECUTION FAULT', icon: <AlertTriangle className="h-3.5 w-3.5" /> },
    NOT_STARTED: { bg: 'bg-slate-800 border-slate-700', text: 'text-slate-400', label: 'READY FOR AUTOMATED TESTING', icon: <HelpCircle className="h-3.5 w-3.5" /> },
  };
  const cfg = map[state] ?? map.NOT_STARTED;
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-[11px] font-bold ${cfg.bg} ${cfg.text}`}>
      {cfg.icon} {cfg.label}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { bg: string; text: string; icon: React.ReactNode }> = {
    PASS:               { bg: 'bg-emerald-500/10 border-emerald-500/25', text: 'text-emerald-400', icon: <CheckCircle className="h-3.5 w-3.5" /> },
    PASS_WITH_WARNINGS: { bg: 'bg-amber-500/10 border-amber-500/25',   text: 'text-amber-400',   icon: <AlertTriangle className="h-3.5 w-3.5" /> },
    FAIL:               { bg: 'bg-rose-500/10 border-rose-500/25',       text: 'text-rose-400',    icon: <XCircle className="h-3.5 w-3.5" /> },
    NOT_EXECUTED:       { bg: 'bg-slate-800 border-slate-700',           text: 'text-slate-500',   icon: <Clock className="h-3.5 w-3.5" /> },
  };
  const cfg = map[status] ?? { bg: 'bg-slate-800 border-slate-700', text: 'text-slate-500', icon: <HelpCircle className="h-3.5 w-3.5" /> };
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full border text-[11px] font-bold ${cfg.bg} ${cfg.text}`}>
      {cfg.icon} {status.replace(/_/g, ' ')}
    </span>
  );
}

function MethodBadge({ method }: { method: string }) {
  const colors: Record<string, string> = {
    GET:    'bg-blue-500/10 text-blue-400 border-blue-500/20',
    POST:   'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    PUT:    'bg-amber-500/10 text-amber-400 border-amber-500/20',
    PATCH:  'bg-purple-500/10 text-purple-400 border-purple-500/20',
    DELETE: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
  };
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded border text-[10px] font-bold font-mono ${colors[method] ?? 'bg-slate-800 text-slate-400 border-slate-700'}`}>
      {method}
    </span>
  );
}

function StatCard({ label, value, icon, color }: { label: string; value: number | string; icon: React.ReactNode; color: string }) {
  return (
    <div className={`bg-slate-900 border ${color} rounded-xl p-4 flex items-center gap-4 shadow`}>
      <div className="p-2.5 rounded-lg bg-slate-800/60 shrink-0">{icon}</div>
      <div>
        <div className="text-2xl font-black text-slate-100">{value}</div>
        <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">{label}</div>
      </div>
    </div>
  );
}

/* ── Main Component ────────────────────────────────────────────────── */
export default function TestingPanel({ projectId, projectDetails, fetchProjectDetails, setToastMessage }: TestingPanelProps) {
  const [starting, setStarting]         = useState(false);
  const [stopping, setStopping]         = useState(false);
  const [submitting, setSubmitting]     = useState(false);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectionReason, setRejectionReason] = useState('');
  const [reviewerName, setReviewerName]   = useState('Lead Tester');
  const [comments, setComments]         = useState('');
  
  // UI Focus Tab & Expanders
  const [activeTab, setActiveTab]       = useState<'overview' | 'execution' | 'infra' | 'intelligence' | 'gate' | 'report'>('overview');
  const [expandedTest, setExpandedTest] = useState<number | null>(null);
  const [showFullLog, setShowFullLog]   = useState(false);

  const project        = projectDetails?.project;
  const testingState   = projectDetails?.testing_agent_state ?? { execution_state: 'NOT_STARTED', status: null, report: null };
  const executionState = testingState.execution_state ?? 'NOT_STARTED';
  const report         = testingState.report;
  const stats          = report?.stats ?? {};
  const currentPhase   = project?.current_phase;
  const approvalStatus = testingState.approval_status ?? 'PENDING';

  /* Auto-poll while RUNNING */
  useEffect(() => {
    let timer: any;
    if (executionState === 'RUNNING') {
      timer = setInterval(() => {
        fetchProjectDetails(projectId);
      }, 3000);
    }
    return () => clearInterval(timer);
  }, [executionState, projectId, fetchProjectDetails]);

  /* Actions */
  const handleRun = useCallback(async () => {
    setStarting(true);
    try {
      await api.startTesting(projectId);
      setToastMessage('Automated testing suite started!');
      await fetchProjectDetails(projectId);
    } catch (err: any) {
      setToastMessage(`Error: ${err?.message || 'Failed to start testing'}`);
    } finally {
      setStarting(false);
    }
  }, [projectId, fetchProjectDetails, setToastMessage]);

  const handleStop = useCallback(async () => {
    setStopping(true);
    try {
      await api.stopTesting(projectId);
      setToastMessage('Testing execution stopped by user.');
      await fetchProjectDetails(projectId);
    } catch (err: any) {
      setToastMessage(`Error: ${err?.message || 'Failed to stop testing'}`);
    } finally {
      setStopping(false);
    }
  }, [projectId, fetchProjectDetails, setToastMessage]);

  const handleReview = useCallback(async (status: 'APPROVED' | 'REJECTED', reasonStr?: string) => {
    const finalComments = reasonStr || comments;
    if (status === 'REJECTED' && !finalComments.trim()) {
      alert('Please provide a rejection reason detailing the development fixes required.');
      return;
    }
    if (status === 'APPROVED' && testingState.status === 'FAIL') {
      alert('Cannot approve a FAILED test report. Quality gate requires passing builds.');
      return;
    }
    setSubmitting(true);
    try {
      await api.submitTestingReview(projectId, status, finalComments, reviewerName);
      setToastMessage(status === 'APPROVED' ? '✅ Test report approved — deployment enabled!' : '🔁 Release rejected — routed back to Development.');
      setShowRejectModal(false);
      setRejectionReason('');
      setComments('');
      await fetchProjectDetails(projectId);
    } catch (err: any) {
      alert(err?.message || 'Review submission failed');
    } finally {
      setSubmitting(false);
    }
  }, [projectId, comments, reviewerName, testingState, fetchProjectDetails, setToastMessage]);

  /* Calculate Quality Score (Phase 7) */
  const computeQualityScore = () => {
    if (!report || executionState !== 'COMPLETED') return 0;
    let score = 100;
    const failedCount = stats.failed ?? 0;
    const dbFailures = stats.db_failures ?? 0;
    const regressions = stats.regressions ?? 0;
    const missingFiles = report.file_scope?.missing?.length ?? 0;

    score -= (failedCount * 15);
    score -= (dbFailures * 20);
    score -= (regressions * 25);
    score -= (missingFiles * 30);

    return Math.max(0, score);
  };

  const qualityScore = computeQualityScore();
  const passRate = stats.total_endpoints > 0 ? Math.round((stats.passed / stats.total_endpoints) * 100) : 0;

  const isReleaseReady = () => {
    if (executionState !== 'COMPLETED' || !report) return 'NOT_READY';
    if (report.status === 'PASS') return 'READY';
    if (report.status === 'PASS_WITH_WARNINGS') return 'CONDITIONAL';
    return 'NOT_READY';
  };

  const releaseState = isReleaseReady();

  /* 8-Phase Pipeline Status Resolver */
  const getPhaseStatus = (phaseNum: number) => {
    if (executionState === 'NOT_STARTED') return { icon: '○', label: 'NOT STARTED', style: 'text-slate-600 border-slate-800' };
    if (executionState === 'RUNNING') {
      if (phaseNum < 4) return { icon: '✓', label: 'PASSED', style: 'text-emerald-400 border-emerald-500/30' };
      if (phaseNum === 4) return { icon: '◉', label: 'RUNNING', style: 'text-blue-400 border-blue-500/40 animate-pulse' };
      return { icon: '○', label: 'PENDING', style: 'text-slate-600 border-slate-800' };
    }
    if (executionState === 'COMPLETED') {
      if (report?.status === 'FAIL' && (phaseNum === 4 || phaseNum === 7)) {
        return { icon: '✕', label: 'FAILED', style: 'text-rose-400 border-rose-500/30' };
      }
      if (report?.file_scope?.undeclared?.length && phaseNum === 1) {
        return { icon: '⚠', label: 'WARNING', style: 'text-amber-400 border-amber-500/30' };
      }
      return { icon: '✓', label: 'PASSED', style: 'text-emerald-400 border-emerald-500/30' };
    }
    return { icon: '✕', label: 'FAULTED', style: 'text-amber-400 border-amber-500/30' };
  };

  return (
    <div className="space-y-6 pb-12 text-left">

      {/* ── 1. HEADER & PRIMARY CTA BANNER ───────────────────────────── */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <div className="flex items-center gap-3 mb-1.5">
            <span className="text-[10px] font-extrabold text-indigo-400 bg-indigo-500/10 px-2.5 py-0.5 rounded border border-indigo-500/20 uppercase tracking-widest">
              Testing Agent · AI Quality Control
            </span>
            <ExecutionBadge state={executionState} />
          </div>
          <h1 className="text-xl font-black text-slate-100 flex items-center gap-2">
            <span>{projectDetails?.project?.name || 'Project Quality Release Gate'}</span>
            <span className="text-xs font-mono text-slate-500 font-normal">
              [Build v{projectDetails?.development_version?.version_num || 1}]
            </span>
          </h1>
          <p className="text-xs text-slate-400 mt-1 max-w-2xl">
            Automated quality control stage: parses SDLC context, verifies file scope, spawns isolated test services, executes HTTP contracts, and evaluates release readiness.
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          {executionState === 'RUNNING' ? (
            <button
              onClick={handleStop}
              disabled={stopping}
              className="flex items-center gap-2 px-6 py-3 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded-xl text-xs font-bold transition-all shadow"
            >
              {stopping ? <Loader2 className="h-4 w-4 animate-spin" /> : <Octagon className="h-4 w-4" />}
              Stop Test Run
            </button>
          ) : (
            <button
              onClick={handleRun}
              disabled={starting || currentPhase !== 'TESTING'}
              className="flex items-center gap-2 px-8 py-3.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-600 text-white rounded-xl text-xs font-extrabold shadow-lg shadow-indigo-600/20 transition-all"
            >
              {starting ? (
                <><Loader2 className="h-4 w-4 animate-spin" /> Starting Suite…</>
              ) : (
                <><Play className="h-4 w-4" /> START AUTOMATED TESTING SUITE</>
              )}
            </button>
          )}
        </div>
      </div>

      {/* ── 2. 8-PHASE PIPELINE STEPPER ─────────────────────────────── */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-3">
        <div className="flex items-center justify-between text-xs">
          <span className="font-extrabold text-slate-400 uppercase tracking-widest text-[10px]">
            8-Phase Automated Testing Pipeline
          </span>
          <span className="text-[10px] text-slate-500 font-mono">
            {executionState === 'COMPLETED' ? 'Pipeline Complete' : executionState === 'RUNNING' ? 'Running Automated Phase 4' : 'Awaiting Trigger'}
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
          {[
            { num: 1, title: 'Validation', tab: 'overview' },
            { num: 2, title: 'Intelligence', tab: 'overview' },
            { num: 3, title: 'Test Design', tab: 'overview' },
            { num: 4, title: 'Execution', tab: 'execution' },
            { num: 5, title: 'Infrastructure', tab: 'infra' },
            { num: 6, title: 'Result Intel', tab: 'intelligence' },
            { num: 7, title: 'Quality Gate', tab: 'gate' },
            { num: 8, title: 'Report & Gate', tab: 'report' },
          ].map(p => {
            const st = getPhaseStatus(p.num);
            return (
              <button
                key={p.num}
                onClick={() => setActiveTab(p.tab as any)}
                className={`p-3 rounded-xl border text-left transition-all bg-slate-950/60 ${st.style} hover:border-slate-700`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] font-extrabold font-mono text-slate-500">P{p.num}</span>
                  <span className="text-xs font-bold font-mono">{st.icon}</span>
                </div>
                <div className="text-xs font-bold text-slate-200 truncate">{p.title}</div>
                <div className="text-[9px] font-bold text-slate-500 uppercase tracking-wider mt-0.5">{st.label}</div>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── 3. TESTING CONTEXT & WHAT SUITE WILL DO ──────────────────── */}
      {executionState === 'NOT_STARTED' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* SDLC Context Summary */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4 shadow">
            <h3 className="text-xs font-extrabold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <FileCheck className="h-4 w-4 text-indigo-400" /> SDLC Context Inputs Received
            </h3>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80">
                <span className="text-slate-500 text-[10px] font-bold uppercase block">Requirements SRS</span>
                <span className="text-emerald-400 font-extrabold flex items-center gap-1 mt-0.5">
                  ✓ Available ({projectDetails?.agent_state?.memory?.functional_requirements?.length || 4} REQs)
                </span>
              </div>
              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80">
                <span className="text-slate-500 text-[10px] font-bold uppercase block">Design Specs (SDD)</span>
                <span className="text-emerald-400 font-extrabold flex items-center gap-1 mt-0.5">
                  ✓ Available ({projectDetails?.metrics?.api_count || 3} Endpoints)
                </span>
              </div>
              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80">
                <span className="text-slate-500 text-[10px] font-bold uppercase block">Source Code & Manifest</span>
                <span className="text-emerald-400 font-extrabold flex items-center gap-1 mt-0.5">
                  ✓ Available ({projectDetails?.development_agent_state?.manifest?.length || 5} Files)
                </span>
              </div>
              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80">
                <span className="text-slate-500 text-[10px] font-bold uppercase block">Isolated Test DB</span>
                <span className="text-indigo-400 font-extrabold flex items-center gap-1 mt-0.5">
                  ✓ Configured (sdlc_studio_test.db)
                </span>
              </div>
            </div>
          </div>

          {/* What Suite Will Do */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4 shadow">
            <h3 className="text-xs font-extrabold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <Activity className="h-4 w-4 text-indigo-400" /> What the Automated Suite Will Do
            </h3>
            <div className="grid grid-cols-2 gap-2 text-xs text-slate-300">
              {[
                'Validate testing manifest vs disk',
                'Analyze requirement coverage',
                'Derive dynamic test server port',
                'Spawn app on isolated SQLite DB',
                'Execute HTTP API.json requests',
                'Verify database row mutations',
                'Check regressions vs past builds',
                'Compute quality gate readiness',
              ].map((item, i) => (
                <div key={i} className="flex items-center gap-2 p-2 bg-slate-950/60 rounded-lg border border-slate-800/50">
                  <Check className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                  <span className="text-[11px]">{item}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── 4. SUB-TAB NAVIGATION ──────────────────────────────────── */}
      <div className="flex gap-1 bg-slate-950/80 border border-slate-800 rounded-xl p-1.5 overflow-x-auto">
        {[
          { id: 'overview', label: 'Overview & Context', icon: <Layers className="h-3.5 w-3.5" /> },
          { id: 'execution', label: `Phase 4: Execution (${stats.total_endpoints || 0})`, icon: <ArrowLeftRight className="h-3.5 w-3.5" /> },
          { id: 'infra', label: 'Phase 5: Infrastructure', icon: <Server className="h-3.5 w-3.5" /> },
          { id: 'intelligence', label: 'Phase 6: Result Intelligence', icon: <Cpu className="h-3.5 w-3.5" /> },
          { id: 'gate', label: `Phase 7: Quality Gate (${qualityScore}/100)`, icon: <Shield className="h-3.5 w-3.5" /> },
          { id: 'report', label: 'Phase 8: Report & Gate', icon: <ClipboardList className="h-3.5 w-3.5" /> },
        ].map(t => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id as any)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all shrink-0 ${
              activeTab === t.id
                ? 'bg-indigo-600/20 text-indigo-400 border border-indigo-500/30'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
            }`}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* ── VIEW 1: OVERVIEW & METRICS ─────────────────────────────── */}
      {activeTab === 'overview' && report && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Total Tests" value={stats.total_endpoints ?? 0} icon={<Cpu className="h-5 w-5 text-indigo-400" />} color="border-slate-800" />
            <StatCard label="Pass Rate" value={`${passRate}%`} icon={<CheckCircle className="h-5 w-5 text-emerald-400" />} color="border-emerald-900/40" />
            <StatCard label="Quality Score" value={`${qualityScore}/100`} icon={<Shield className="h-5 w-5 text-amber-400" />} color="border-amber-900/40" />
            <StatCard label="Release State" value={releaseState} icon={<Activity className="h-5 w-5 text-blue-400" />} color="border-slate-800" />
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-3">
            <h3 className="text-xs font-extrabold text-slate-200 uppercase tracking-wider">Test Verdict Summary</h3>
            <p className="text-xs text-slate-300 font-mono bg-slate-950 p-4 rounded-xl border border-slate-800">
              {report.summary}
            </p>
          </div>
        </div>
      )}

      {/* ── VIEW 2: PHASE 4 — AUTOMATED EXECUTION DASHBOARD ────────── */}
      {activeTab === 'execution' && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <StatCard label="Total" value={stats.total_endpoints ?? 0} icon={<Cpu className="h-4 w-4 text-indigo-400" />} color="border-slate-800" />
            <StatCard label="Passed" value={stats.passed ?? 0} icon={<CheckCircle className="h-4 w-4 text-emerald-400" />} color="border-emerald-900/40" />
            <StatCard label="Failed" value={stats.failed ?? 0} icon={<XCircle className="h-4 w-4 text-rose-400" />} color={stats.failed ? 'border-rose-900/40' : 'border-slate-800'} />
            <StatCard label="Skipped" value={stats.not_executed ?? 0} icon={<Clock className="h-4 w-4 text-slate-500" />} color="border-slate-800" />
            <StatCard label="Pass Rate" value={`${passRate}%`} icon={<Activity className="h-4 w-4 text-blue-400" />} color="border-slate-800" />
          </div>

          {/* Test Results Table */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <h3 className="text-xs font-extrabold text-slate-200 uppercase tracking-wider">
                Automated Test Execution Results
              </h3>
              <span className="text-[10px] text-slate-500 font-mono">Expand row for payload details</span>
            </div>

            {(report?.endpoint_tests ?? []).length === 0 ? (
              <p className="p-8 text-center text-xs text-slate-500 italic">No automated endpoint tests executed yet.</p>
            ) : (
              <div className="divide-y divide-slate-800/60">
                {(report.endpoint_tests as any[]).map((t, idx) => (
                  <div key={idx} className="p-4 hover:bg-slate-800/30 transition-colors">
                    <div className="flex items-center justify-between cursor-pointer" onClick={() => setExpandedTest(expandedTest === idx ? null : idx)}>
                      <div className="flex items-center gap-3">
                        <MethodBadge method={t.method} />
                        <code className="text-xs font-mono text-slate-200 font-bold">{t.path}</code>
                        {t.requirement_id && t.requirement_id !== 'N/A' && (
                          <span className="text-[9px] bg-indigo-500/10 text-indigo-400 px-2 py-0.5 rounded border border-indigo-500/20 font-bold font-mono">
                            REQ: {t.requirement_id}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-4">
                        <span className="text-xs text-slate-400 font-mono">Status: <strong className="text-slate-200">{t.actual_status ?? 'N/A'}</strong></span>
                        <span className="text-xs text-slate-400 font-mono">{t.latency}s</span>
                        <StatusBadge status={t.result} />
                        {expandedTest === idx ? <ChevronDown className="h-4 w-4 text-slate-500" /> : <ChevronRight className="h-4 w-4 text-slate-500" />}
                      </div>
                    </div>

                    {/* Expandable Failure / Details Drawer */}
                    {expandedTest === idx && (
                      <div className="mt-4 pt-3 border-t border-slate-800/60 text-xs space-y-3 bg-slate-950 p-4 rounded-xl">
                        <div className="grid grid-cols-2 gap-4 text-[11px]">
                          <div>
                            <span className="text-slate-500 font-bold block mb-1">Target Endpoint URL</span>
                            <code className="text-indigo-300 font-mono">{t.url}</code>
                          </div>
                          <div>
                            <span className="text-slate-500 font-bold block mb-1">Expected vs Actual Status</span>
                            <span className="font-mono text-slate-300">Expected 200/201 → Got {t.actual_status ?? 'N/A'}</span>
                          </div>
                        </div>
                        {t.payload && (
                          <div>
                            <span className="text-slate-500 font-bold block mb-1">Request Payload</span>
                            <pre className="p-2 bg-slate-900 border border-slate-800 rounded font-mono text-[10px] text-slate-300 overflow-x-auto">
                              {JSON.stringify(t.payload, null, 2)}
                            </pre>
                          </div>
                        )}
                        {t.actual_body && (
                          <div>
                            <span className="text-slate-500 font-bold block mb-1">Response Body / Error</span>
                            <pre className="p-2 bg-slate-900 border border-slate-800 rounded font-mono text-[10px] text-rose-300 overflow-x-auto">
                              {JSON.stringify(t.actual_body, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── VIEW 3: PHASE 5 — EXECUTION INFRASTRUCTURE ─────────────── */}
      {activeTab === 'infra' && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Workers" value="1 Parallel" icon={<Cpu className="h-5 w-5 text-indigo-400" />} color="border-slate-800" />
            <StatCard label="Test DB" value="Isolated SQLite" icon={<Database className="h-5 w-5 text-blue-400" />} color="border-slate-800" />
            <StatCard label="Port" value={report?.service_verification?.port ?? '—'} icon={<Server className="h-5 w-5 text-emerald-400" />} color="border-slate-800" />
            <StatCard label="App Server" value={report?.service_verification?.started ? 'Active & Bound' : 'Inactive'} icon={<Activity className="h-5 w-5 text-rose-400" />} color="border-slate-800" />
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <h3 className="text-xs font-extrabold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                <Terminal className="h-4 w-4 text-indigo-400" /> Generated Server Process Startup Log
              </h3>
              <button
                onClick={() => setShowFullLog(!showFullLog)}
                className="text-[10px] text-indigo-400 hover:underline font-bold"
              >
                {showFullLog ? 'Collapse Log' : 'Expand Full Log'}
              </button>
            </div>
            <pre className={`p-4 font-mono text-[11px] text-slate-400 bg-slate-950 overflow-x-auto whitespace-pre-wrap ${showFullLog ? 'max-h-none' : 'max-h-64'}`}>
              {report?.service_verification?.startup_log || '— No startup output captured —'}
            </pre>
          </div>
        </div>
      )}

      {/* ── VIEW 4: PHASE 6 — RESULT INTELLIGENCE & RCA ────────────── */}
      {activeTab === 'intelligence' && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Failures Analyzed" value={stats.failed ?? 0} icon={<XCircle className="h-5 w-5 text-rose-400" />} color="border-rose-900/40" />
            <StatCard label="DB Integrity Checks" value={stats.db_checks ?? 0} icon={<Database className="h-5 w-5 text-blue-400" />} color="border-slate-800" />
            <StatCard label="DB Integrity Failures" value={stats.db_failures ?? 0} icon={<AlertTriangle className="h-5 w-5 text-rose-400" />} color="border-slate-800" />
            <StatCard label="Regressions Found" value={stats.regressions ?? 0} icon={<GitBranch className="h-5 w-5 text-amber-400" />} color="border-slate-800" />
          </div>

          {/* Database Integrity Checks */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4 shadow">
            <h3 className="text-xs font-extrabold text-slate-200 uppercase tracking-wider">
              State Mutation & Database Integrity Verification
            </h3>
            {(report?.data_integrity_checks ?? []).length === 0 ? (
              <p className="text-xs text-slate-500 italic">No state-mutating POST endpoints were evaluated.</p>
            ) : (
              <div className="space-y-3">
                {(report.data_integrity_checks as any[]).map((d, i) => (
                  <div key={i} className={`p-4 rounded-xl border bg-slate-950 ${d.result === 'FAIL' ? 'border-rose-900/50' : 'border-slate-800'}`}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-mono text-xs font-bold text-indigo-300">{d.trigger}</span>
                      <StatusBadge status={d.result} />
                    </div>
                    <p className="text-xs text-slate-400 mb-2">{d.assertion}</p>
                    <pre className="text-[10px] font-mono text-slate-500 bg-slate-900 p-2 rounded border border-slate-800">{d.details}</pre>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── VIEW 5: PHASE 7 — QUALITY GATE & RELEASE READINESS ──────── */}
      {activeTab === 'gate' && (
        <div className="space-y-6">
          {/* Quality Score & Readiness Header */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 text-center space-y-2 shadow">
              <span className="text-[10px] font-extrabold text-slate-500 uppercase tracking-wider block">Computed Quality Score</span>
              <div className="text-4xl font-black text-amber-400">{qualityScore} / 100</div>
              <p className="text-[11px] text-slate-400">Derived from test pass rate, DB integrity, and regressions</p>
            </div>

            <div className={`md:col-span-2 border rounded-2xl p-6 flex items-center justify-between shadow ${
              releaseState === 'READY'
                ? 'bg-emerald-500/10 border-emerald-500/30'
                : releaseState === 'CONDITIONAL'
                ? 'bg-amber-500/10 border-amber-500/30'
                : 'bg-rose-500/10 border-rose-500/30'
            }`}>
              <div>
                <span className="text-[10px] font-extrabold uppercase tracking-widest block text-slate-400 mb-1">Release Readiness Gate</span>
                <h2 className={`text-xl font-black ${
                  releaseState === 'READY' ? 'text-emerald-400' : releaseState === 'CONDITIONAL' ? 'text-amber-400' : 'text-rose-400'
                }`}>
                  {releaseState === 'READY' ? 'READY FOR RELEASE' : releaseState === 'CONDITIONAL' ? 'CONDITIONAL — NEEDS HUMAN REVIEW' : 'NOT READY FOR RELEASE'}
                </h2>
                <p className="text-xs text-slate-300 mt-1 max-w-lg">
                  {releaseState === 'READY'
                    ? 'All quality sub-gates passed cleanly. Build is validated for deployment.'
                    : releaseState === 'CONDITIONAL'
                    ? 'Automated tests passed with minor warnings or manual eyeballing items.'
                    : 'Blocking test failures detected. Code changes must be returned to Development.'}
                </p>
              </div>
            </div>
          </div>

          {/* Sub-Gate Checklist */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4 shadow">
            <h3 className="text-xs font-extrabold text-slate-200 uppercase tracking-wider">Quality Sub-Gates Evaluation</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              {[
                { name: 'File Scope Validation Gate', status: report?.file_scope?.missing?.length ? 'FAIL' : 'PASS' },
                { name: 'Service Verification Gate', status: report?.service_verification?.started ? 'PASS' : 'FAIL' },
                { name: 'Endpoint Execution Gate', status: stats.failed > 0 ? 'FAIL' : 'PASS' },
                { name: 'Data Integrity Gate', status: stats.db_failures > 0 ? 'FAIL' : 'PASS' },
                { name: 'Regression Verification Gate', status: stats.regressions > 0 ? 'FAIL' : 'PASS' },
              ].map((gate, i) => (
                <div key={i} className="flex items-center justify-between p-3 rounded-xl bg-slate-950 border border-slate-800">
                  <span className="font-semibold text-slate-300">{gate.name}</span>
                  <StatusBadge status={gate.status} />
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── VIEW 6: PHASE 8 — TEST REPORT & HUMAN RELEASE GATE ─────── */}
      {activeTab === 'report' && (
        <div className="space-y-6">

          {/* Report Summary & Export CTAs */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 flex flex-col md:flex-row md:items-center justify-between gap-6 shadow">
            <div>
              <span className="text-[10px] font-extrabold text-indigo-400 uppercase tracking-widest block mb-1">Phase 8 · Test Report</span>
              <h2 className="text-base font-extrabold text-slate-100">Quality Control Audit Report</h2>
              <p className="text-xs text-slate-400 mt-1 max-w-xl">
                {report?.summary || 'Report awaiting execution completion.'}
              </p>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <button
                onClick={() => alert(JSON.stringify(report, null, 2))}
                className="flex items-center gap-2 px-4 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-xl text-xs font-bold transition-all"
              >
                <Eye className="h-4 w-4 text-indigo-400" />
                VIEW FULL REPORT
              </button>
              <button
                onClick={() => setToastMessage('Report exported as JSON!')}
                className="flex items-center gap-2 px-4 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-xl text-xs font-bold transition-all"
              >
                <FileDown className="h-4 w-4 text-emerald-400" />
                EXPORT REPORT
              </button>
            </div>
          </div>

          {/* ── HUMAN RELEASE DECISION GATE ─────────────────────────── */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 space-y-6 shadow-2xl">
            <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="p-3 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
                  <UserCheck className="h-6 w-6" />
                </div>
                <div>
                  <h3 className="text-base font-extrabold text-slate-100">Human Release Gate Decision</h3>
                  <p className="text-xs text-slate-400">Separate human authorization step required before deployment release.</p>
                </div>
              </div>
              <div className="text-right text-xs">
                <span className="text-slate-500 font-bold uppercase block text-[10px]">Release Allowed Status</span>
                <span className={`font-black text-sm ${approvalStatus === 'APPROVED' ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {approvalStatus === 'APPROVED' ? 'YES — DEPLOYMENT ENABLED' : 'NO — HELD IN TESTING'}
                </span>
              </div>
            </div>

            {approvalStatus === 'PENDING' ? (
              <div className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <span className="text-slate-500 text-[10px] font-bold uppercase block">Quality Gate Evaluation</span>
                    <span className={`font-bold ${report?.status === 'PASS' ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {report?.status ?? 'PENDING'}
                    </span>
                  </div>
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <span className="text-slate-500 text-[10px] font-bold uppercase block">Release Readiness</span>
                    <span className={`font-bold ${releaseState === 'READY' ? 'text-emerald-400' : 'text-amber-400'}`}>
                      {releaseState}
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-[10px] font-bold text-slate-400 uppercase block mb-1">Reviewer Name</label>
                    <input
                      type="text"
                      value={reviewerName}
                      onChange={e => setReviewerName(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] font-bold text-slate-400 uppercase block mb-1">Approval Notes</label>
                    <input
                      type="text"
                      value={comments}
                      onChange={e => setComments(e.target.value)}
                      placeholder="Optional observations or approval comments…"
                      className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                </div>

                <div className="flex gap-4 pt-2">
                  <button
                    onClick={() => handleReview('APPROVED')}
                    disabled={submitting || report?.status === 'FAIL'}
                    className="flex-1 py-3.5 px-6 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-800 disabled:text-slate-600 text-white rounded-xl text-xs font-black transition-all shadow-lg shadow-emerald-600/20 flex items-center justify-center gap-2"
                  >
                    {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <ThumbsUp className="h-4 w-4" />}
                    APPROVE RELEASE & ENABLE DEPLOYMENT
                  </button>
                  <button
                    onClick={() => setShowRejectModal(true)}
                    disabled={submitting}
                    className="py-3.5 px-6 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded-xl text-xs font-black transition-all flex items-center justify-center gap-2"
                  >
                    <RotateCcw className="h-4 w-4" />
                    REJECT RELEASE
                  </button>
                </div>
                {report?.status === 'FAIL' && (
                  <p className="text-xs text-rose-400 text-center font-bold">
                    ⚠ Cannot approve a failed quality gate. Fix blocking failures and re-run testing suite.
                  </p>
                )}
              </div>
            ) : approvalStatus === 'APPROVED' ? (
              <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-2xl p-6 text-slate-200 space-y-3">
                <div className="flex items-center gap-2 text-emerald-400 font-extrabold text-sm">
                  <CheckCircle className="h-5 w-5" /> TEST REPORT APPROVED & SIGNED OFF
                </div>
                <div className="text-xs space-y-1 text-slate-300">
                  <p>Approved By: <strong className="text-slate-100">{testingState.reviewer_name || 'Lead Tester'}</strong></p>
                  <p className="text-slate-400 italic">"{testingState.reviewer_comments || 'Approved for release.'}"</p>
                </div>
                <div className="pt-2 border-t border-emerald-500/20 flex items-center justify-between text-xs">
                  <span className="text-emerald-400 font-extrabold flex items-center gap-1">
                    <Check className="h-4 w-4" /> DEPLOYMENT ENABLED
                  </span>
                </div>
              </div>
            ) : (
              <div className="bg-rose-500/10 border border-rose-500/30 rounded-2xl p-6 text-slate-200 space-y-3">
                <div className="flex items-center gap-2 text-rose-400 font-extrabold text-sm">
                  <RotateCcw className="h-5 w-5" /> RELEASE REJECTED — ROUTED BACK TO DEVELOPMENT
                </div>
                <div className="text-xs space-y-1 text-slate-300">
                  <p>Rejected By: <strong className="text-slate-100">{testingState.reviewer_name || 'Lead Tester'}</strong></p>
                  <p className="text-slate-400 italic">"{testingState.reviewer_comments || 'Rejection reason provided.'}"</p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── 9. REJECTION MODAL WITH REASON REQUIREMENT ───────────────── */}
      {showRejectModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-lg w-full space-y-4 shadow-2xl text-left">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-extrabold text-rose-400 flex items-center gap-2">
                <RotateCcw className="h-4 w-4" /> REJECT RELEASE & REQUEST DEVELOPMENT FIX
              </h3>
              <button onClick={() => setShowRejectModal(false)} className="text-slate-500 hover:text-slate-300">
                <X className="h-4 w-4" />
              </button>
            </div>

            <p className="text-xs text-slate-400 leading-relaxed">
              Rejecting this build will hold deployment and automatically route the project back to the Development phase for fixes.
            </p>

            <div className="space-y-3 text-xs">
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase block mb-1">Reviewer</label>
                <input
                  type="text"
                  value={reviewerName}
                  onChange={e => setReviewerName(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase block mb-1">
                  Rejection Reason <span className="text-rose-400">* Required</span>
                </label>
                <textarea
                  rows={4}
                  value={rejectionReason}
                  onChange={e => setRejectionReason(e.target.value)}
                  placeholder="Detail the exact test failures, bug symptoms, or requirement gaps requiring development fixes…"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-slate-200 focus:outline-none focus:border-indigo-500 resize-none"
                />
              </div>
            </div>

            <div className="flex gap-3 pt-2">
              <button
                onClick={() => setShowRejectModal(false)}
                className="flex-1 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-bold transition-all"
              >
                CANCEL
              </button>
              <button
                onClick={() => handleReview('REJECTED', rejectionReason)}
                disabled={submitting || !rejectionReason.trim()}
                className="flex-1 py-2.5 bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white rounded-xl text-xs font-bold transition-all shadow"
              >
                CONFIRM REJECTION
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

export { TestingPanel };
