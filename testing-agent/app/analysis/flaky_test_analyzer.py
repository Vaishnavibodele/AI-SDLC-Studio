"""Phase 6 flaky test detection.

Flakiness is only reported when inconsistent outcomes were actually observed,
either across the Phase 5 retry attempts of a result or across supplied
historical execution reports for the same test case. A single recorded outcome
is never reported as flaky.
"""
from typing import Any, Dict, Iterable, List, Optional

from app.analysis.schemas import (
    INSUFFICIENT_HISTORY_REASON,
    Confidence,
    FlakyTestAnalysis,
)

_PASSING = {"PASS"}
_FAILING = {"FAIL", "ERROR"}


def _attempt_statuses(result: Dict[str, Any]) -> List[str]:
    entries = result.get("attempts_detail") or result.get("logs") or []
    statuses: List[str] = []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("status"):
            statuses.append(str(entry["status"]).upper())
    if not statuses and result.get("status"):
        statuses.append(str(result["status"]).upper())
    return statuses


def _history_statuses(
    test_case_id: str,
    history: Optional[Iterable[Dict[str, Any]]],
) -> List[str]:
    """Statuses recorded for the same test case in previous executions."""
    statuses: List[str] = []
    for record in history or []:
        if not isinstance(record, dict):
            continue
        results = record.get("results") if "results" in record else [record]
        for res in results or []:
            if not isinstance(res, dict):
                continue
            if str(res.get("test_case_id")) != test_case_id:
                continue
            statuses.extend(_attempt_statuses(res))
    return statuses


def analyze_result(
    result: Dict[str, Any],
    history: Optional[Iterable[Dict[str, Any]]] = None,
) -> FlakyTestAnalysis:
    """Assess flakiness for a single Phase 5 execution result."""
    test_case_id = str(result.get("test_case_id") or "unknown")
    run_id = result.get("run_id")
    statuses = _history_statuses(test_case_id, history) + _attempt_statuses(result)
    observed = set(statuses)

    if len(statuses) < 2:
        return FlakyTestAnalysis(
            test_case_id=test_case_id,
            flaky=False,
            confidence=Confidence.LOW,
            reason=INSUFFICIENT_HISTORY_REASON,
            evidence=[],
            observed_statuses=statuses,
            run_id=run_id,
        )

    if observed & _PASSING and observed & _FAILING:
        return FlakyTestAnalysis(
            test_case_id=test_case_id,
            flaky=True,
            confidence=Confidence.MEDIUM if len(statuses) < 3 else Confidence.HIGH,
            reason=(
                "Inconsistent outcomes observed across "
                f"{len(statuses)} recorded attempts/executions"
            ),
            evidence=[" -> ".join(statuses)],
            observed_statuses=statuses,
            run_id=run_id,
        )

    return FlakyTestAnalysis(
        test_case_id=test_case_id,
        flaky=False,
        confidence=Confidence.MEDIUM,
        reason=f"Consistent outcomes across {len(statuses)} recorded attempts/executions",
        evidence=[" -> ".join(statuses)],
        observed_statuses=statuses,
        run_id=run_id,
    )


def analyze_results(
    results: List[Dict[str, Any]],
    history: Optional[Iterable[Dict[str, Any]]] = None,
) -> List[FlakyTestAnalysis]:
    analyses: List[FlakyTestAnalysis] = []
    for result in results or []:
        if isinstance(result, dict):
            analyses.append(analyze_result(result, history=history))
    return analyses
