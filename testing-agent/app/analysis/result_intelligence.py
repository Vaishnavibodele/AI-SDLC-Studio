"""Phase 6 Result Intelligence orchestrator.

Consumes the Phase 5 execution report produced by `ExecutionController` and
returns an aggregated `ResultIntelligenceReport`:

    execution report -> failure analysis -> root cause analysis
                     -> defect classification -> flaky detection -> report

The pipeline is deterministic and never modifies execution statuses.
"""
import logging
from typing import Any, Dict, Iterable, List, Optional

from app.analysis import defect_analyzer, failure_analyzer, flaky_test_analyzer, root_cause_analyzer
from app.analysis.schemas import ResultIntelligenceReport

logger = logging.getLogger(__name__)


class ResultIntelligence:
    """Single Phase 6 analysis layer over Phase 5 execution reports."""

    def analyze(
        self,
        execution_report: Optional[Dict[str, Any]],
        history: Optional[Iterable[Dict[str, Any]]] = None,
    ) -> ResultIntelligenceReport:
        report = execution_report or {}
        results: List[Dict[str, Any]] = [r for r in (report.get("results") or []) if isinstance(r, dict)]
        run_id = report.get("run_id") or next((r.get("run_id") for r in results if r.get("run_id")), None)

        failures = failure_analyzer.analyze_results(results)
        root_causes = root_cause_analyzer.analyze_failures(failures)
        defects = defect_analyzer.analyze_failures(failures, root_causes)
        flaky = [f for f in flaky_test_analyzer.analyze_results(results, history=history) if f.flaky]

        return ResultIntelligenceReport(
            run_id=run_id,
            analyzed_count=len(results),
            failures_analyzed=len(failures),
            defects_detected=sum(1 for d in defects if d.defect_detected),
            flaky_tests_detected=len(flaky),
            failures=failures,
            root_causes=root_causes,
            defects=defects,
            flaky_tests=flaky,
        )


result_intelligence = ResultIntelligence()


def analyze_execution_report(
    execution_report: Optional[Dict[str, Any]],
    history: Optional[Iterable[Dict[str, Any]]] = None,
) -> ResultIntelligenceReport:
    """Module level helper mirroring `ResultIntelligence.analyze`."""
    return result_intelligence.analyze(execution_report, history=history)
