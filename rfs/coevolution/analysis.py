from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

from .storage import atomic_json, read_json


SCORE_KEYS = ("scientific_score", "aesthetic_score", "visual_quality_score", "total_score")


def _round_summaries(run_dir: Path) -> list[dict]:
    summaries = []
    for path in sorted((run_dir / "rounds").glob("round_*/round_summary.json")):
        value = read_json(path)
        if isinstance(value, dict):
            summaries.append(value)
    return summaries


def _score(evaluation: dict | None, key: str) -> float:
    return round(float((evaluation or {}).get(key, 0.0)), 4)


def _delta(first: dict | None, last: dict | None, key: str) -> float:
    return round(_score(last, key) - _score(first, key), 4)


def analyze_coevolution_run(run_dir: str | Path, write: bool = True) -> dict:
    """Aggregate one completed or interrupted co-evolution run into reproducible metrics."""
    root = Path(run_dir).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Co-evolution run directory does not exist: {root}")

    manifest = read_json(root / "run_manifest.json")
    if not isinstance(manifest, dict):
        raise ValueError(f"Missing or invalid run_manifest.json in {root}")
    summaries = _round_summaries(root)
    if not summaries:
        raise ValueError(f"No committed round summaries found in {root}")

    accepted = [item for item in summaries if item.get("accepted_as_best")]
    outcomes = [item["critique_outcome"] for item in summaries if isinstance(item.get("critique_outcome"), dict)]
    effective = [item for item in outcomes if item.get("feedback_effective")]
    first_eval = summaries[0].get("selected_frozen_evaluation") or {}
    best_evaluations = [item.get("selected_frozen_evaluation") or {} for item in accepted]
    final_eval = best_evaluations[-1] if best_evaluations else first_eval

    initial_blockers = len(first_eval.get("blocking_issues", []) or [])
    final_blockers = len(final_eval.get("blocking_issues", []) or [])
    candidate_count = sum(len(item.get("candidates", []) or []) for item in summaries)
    repair_requests = sum(len(item.get("requested_repairs", []) or []) for item in outcomes)
    side_effect_count = sum(len(item.get("side_effects", []) or []) for item in outcomes)
    score_trajectory = [
        {
            "round": item.get("round"),
            "accepted_as_best": bool(item.get("accepted_as_best")),
            **{key: _score(item.get("selected_frozen_evaluation"), key) for key in SCORE_KEYS},
            "blocking_issues": len((item.get("selected_frozen_evaluation") or {}).get("blocking_issues", []) or []),
        }
        for item in summaries
    ]

    report = {
        "summary": "Co-evolution reproduction metrics.",
        "ok": True,
        "run_dir": str(root),
        "ground_truth_hash": manifest.get("ground_truth_hash"),
        "rounds_committed": len(summaries),
        "candidates_generated": candidate_count,
        "accepted_rounds": len(accepted),
        "acceptance_rate": round(len(accepted) / len(summaries), 4),
        "repair_rounds": len(outcomes),
        "feedback_effective_rounds": len(effective),
        "feedback_effectiveness_rate": round(len(effective) / len(outcomes), 4) if outcomes else None,
        "repair_requests": repair_requests,
        "side_effect_count": side_effect_count,
        "initial_blocking_issues": initial_blockers,
        "final_blocking_issues": final_blockers,
        "blocking_issues_resolved": initial_blockers - final_blockers,
        "initial_scores": {key: _score(first_eval, key) for key in SCORE_KEYS},
        "final_scores": {key: _score(final_eval, key) for key in SCORE_KEYS},
        "score_gains": {key: _delta(first_eval, final_eval, key) for key in SCORE_KEYS},
        "mean_selected_frozen_total_score": round(mean(item["total_score"] for item in score_trajectory), 4),
        "score_trajectory": score_trajectory,
        "online_judge_model": manifest.get("online_judge_model"),
        "frozen_judge_model": manifest.get("frozen_judge_model"),
        "weak_judge_isolation": bool(manifest.get("weak_judge_isolation")),
        "independent_acceptance_configured": not bool(manifest.get("weak_judge_isolation")),
        "limitations": [],
    }
    if report["weak_judge_isolation"]:
        report["limitations"].append("Online and Frozen Judge use the same model, so acceptance is not independent.")
    if len(summaries) == 1:
        report["limitations"].append("Only one committed round exists, so iterative improvement was not measured.")
    if not outcomes:
        report["limitations"].append("No repair outcome exists, so feedback effectiveness cannot be estimated.")

    if write:
        atomic_json(root / "reproduction_metrics.json", report)
        lines = [
            "# Co-evolution Reproduction Metrics",
            "",
            f"- Rounds: {report['rounds_committed']}",
            f"- Candidates: {report['candidates_generated']}",
            f"- Acceptance rate: {report['acceptance_rate']:.1%}",
            f"- Feedback effectiveness: {report['feedback_effectiveness_rate']:.1%}" if report["feedback_effectiveness_rate"] is not None else "- Feedback effectiveness: N/A",
            f"- Total-score gain: {report['score_gains']['total_score']:+.4f}",
            f"- Scientific-score gain: {report['score_gains']['scientific_score']:+.4f}",
            f"- Blocking issues resolved: {report['blocking_issues_resolved']}",
            f"- Independent judge isolation: {'no' if report['weak_judge_isolation'] else 'yes'}",
            "",
            "## Limitations",
            "",
        ]
        lines.extend(f"- {item}" for item in report["limitations"])
        if not report["limitations"]:
            lines.append("- None detected by the run analyzer.")
        (root / "reproduction_metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report
