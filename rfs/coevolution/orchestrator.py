from __future__ import annotations

import json
import hashlib
import shutil
from pathlib import Path
from typing import Any

from .creator import CreatorAgent
from .analysis import analyze_coevolution_run
from .groundtruth import load_ground_truth
from .judges import Judge, VLMJudge
from .providers import ImageProvider, OpenAICompatibleImageProvider
from .storage import atomic_json, read_json


def _evaluation(result: dict, candidate_alias: str) -> dict:
    for item in result.get("evaluations", []):
        if item.get("candidate_id") == candidate_alias:
            return item
    raise ValueError(f"Judge result has no evaluation for {candidate_alias}")


def _selected(result: dict, candidates: list[dict]) -> tuple[dict, dict]:
    ranking = result.get("ranking") or []
    if not ranking:
        raise ValueError("Judge result has an empty ranking")
    alias = str(ranking[0])
    candidate_id = result.get("alias_to_candidate", {}).get(alias, alias)
    by_id = {item["candidate_id"]: item for item in candidates}
    if candidate_id not in by_id:
        raise ValueError(f"Judge selected unknown candidate: {candidate_id}")
    return by_id[candidate_id], _evaluation(result, alias)


def _single_frozen_evaluation(result: dict) -> dict:
    ranking = result.get("ranking") or []
    if not ranking:
        raise ValueError("Frozen Judge result has an empty ranking")
    return _evaluation(result, str(ranking[0]))


def _passes(evaluation: dict, thresholds: dict) -> bool:
    return (
        not evaluation.get("blocking_issues")
        and float(evaluation.get("total_score", 0)) >= thresholds["total"]
        and float(evaluation.get("scientific_score", 0)) >= thresholds["scientific"]
        and float(evaluation.get("aesthetic_score", 0)) >= thresholds["aesthetic"]
    )


def _is_improvement(previous: dict, current: dict) -> bool:
    previous_blocker_set = set(str(item) for item in previous.get("blocking_issues", []))
    current_blocker_set = set(str(item) for item in current.get("blocking_issues", []))
    if current_blocker_set - previous_blocker_set:
        return False
    previous_blockers = len(previous_blocker_set)
    current_blockers = len(current_blocker_set)
    if current_blockers < previous_blockers:
        return True
    if current_blockers > previous_blockers:
        return False
    return (
        float(current.get("total_score", 0)) > float(previous.get("total_score", 0)) + 0.001
        and float(current.get("scientific_score", 0)) >= float(previous.get("scientific_score", 0)) - 0.02
    )


def _outcome(previous: dict, current: dict, feedback: dict, accepted: bool, round_index: int) -> dict:
    dimensions = ("scientific_score", "aesthetic_score", "visual_quality_score", "total_score")
    deltas = {key: round(float(current.get(key, 0)) - float(previous.get(key, 0)), 4) for key in dimensions}
    previous_blockers = set(str(item) for item in previous.get("blocking_issues", []))
    current_blockers = set(str(item) for item in current.get("blocking_issues", []))
    side_effects = [key for key, delta in deltas.items() if key != "total_score" and delta < -0.02]
    side_effects.extend(f"new_blocker:{item}" for item in sorted(current_blockers - previous_blockers))
    return {
        "round": round_index,
        "requested_repairs": feedback.get("repair", []),
        "preserve": feedback.get("preserve", []),
        "score_deltas": deltas,
        "blocking_issue_delta": len(current_blockers) - len(previous_blockers),
        "side_effects": side_effects,
        "accepted_as_best": accepted,
        "feedback_effective": bool(accepted and deltas["total_score"] > 0 and not side_effects),
    }


def _preference_records(round_index: int, online_result: dict, candidates: list[dict], ground_truth_hash: str) -> list[dict]:
    ranking = online_result.get("ranking") or []
    if not ranking:
        return []
    alias_map = online_result.get("alias_to_candidate", {})
    chosen_id = alias_map.get(str(ranking[0]), str(ranking[0]))
    paths = {item["candidate_id"]: item["path"] for item in candidates}
    records = []
    for alias in ranking[1:]:
        rejected_id = alias_map.get(str(alias), str(alias))
        if chosen_id in paths and rejected_id in paths:
            records.append({
                "round": round_index,
                "ground_truth_hash": ground_truth_hash,
                "chosen_candidate_id": chosen_id,
                "chosen_path": paths[chosen_id],
                "rejected_candidate_id": rejected_id,
                "rejected_path": paths[rejected_id],
                "judge_model": online_result.get("model"),
            })
    return records


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")
    temp.replace(path)


def _rebuild_datasets(out: Path) -> None:
    preferences: list[dict] = []
    repairs: list[dict] = []
    outcomes: list[dict] = []
    for summary_path in sorted((out / "rounds").glob("round_*/round_summary.json")):
        summary = read_json(summary_path, {})
        preferences.extend(summary.get("preference_pairs", []))
        if summary.get("repair_trajectory"):
            repairs.append(summary["repair_trajectory"])
        if summary.get("critique_outcome"):
            outcomes.append(summary["critique_outcome"])
    _write_jsonl(out / "preference_pairs.jsonl", preferences)
    _write_jsonl(out / "repair_trajectories.jsonl", repairs)
    _write_jsonl(out / "critique_outcomes.jsonl", outcomes)


def _recover_committed_rounds(out: Path, state: dict) -> dict:
    while True:
        summary_path = out / "rounds" / f"round_{int(state['next_round']):02d}" / "round_summary.json"
        summary = read_json(summary_path)
        if not summary or not isinstance(summary.get("state_after"), dict):
            return state
        state = summary["state_after"]
        atomic_json(out / "run_state.json", state)


def run_image_coevolution(
    ground_truth_path: str | Path,
    out_dir: str | Path,
    candidates: int = 3,
    repair_candidates: int = 2,
    max_rounds: int = 4,
    online_judge_model: str | None = None,
    frozen_judge_model: str | None = None,
    image_model: str | None = None,
    image_retries: int = 2,
    provider: ImageProvider | None = None,
    online_judge: Judge | None = None,
    frozen_judge: Judge | None = None,
) -> dict:
    ground_truth = load_ground_truth(ground_truth_path)
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    candidates = max(1, min(8, int(candidates)))
    repair_candidates = max(1, min(8, int(repair_candidates)))
    max_rounds = max(1, min(20, int(max_rounds)))

    ground_truth_hash = hashlib.sha256(json.dumps(ground_truth, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    existing_manifest = read_json(out / "run_manifest.json")
    requested_identity = {
        "ground_truth_hash": ground_truth_hash,
        "candidates": candidates,
        "repair_candidates": repair_candidates,
        "max_rounds": max_rounds,
    }
    if isinstance(existing_manifest, dict):
        existing_identity = {key: existing_manifest.get(key) for key in requested_identity}
        if existing_identity != requested_identity:
            raise ValueError("Output directory already belongs to a different Ground Truth or co-evolution configuration")
        existing_report = read_json(out / "run_report.json")
        if isinstance(existing_report, dict) and existing_report.get("completed"):
            return existing_report

    provider = provider or OpenAICompatibleImageProvider(model=image_model, retries=image_retries)
    online_judge = online_judge or VLMJudge(model=online_judge_model, frozen=False)
    frozen_judge = frozen_judge or VLMJudge(model=frozen_judge_model, frozen=True)
    creator = CreatorAgent(provider)
    online_model = getattr(online_judge, "model_name", online_judge.__class__.__name__)
    frozen_model = getattr(frozen_judge, "model_name", frozen_judge.__class__.__name__)
    weak_isolation = online_model == frozen_model

    snapshot_path = out / "ground_truth_snapshot.json"
    if not snapshot_path.exists():
        atomic_json(snapshot_path, ground_truth)
    manifest = {
        "summary": "Whole-image Creator Agent and Judge Model co-evolution run.",
        "ground_truth_source": ground_truth["source_path"],
        "ground_truth_hash": ground_truth_hash,
        "online_judge_model": online_model,
        "frozen_judge_model": frozen_model,
        "weak_judge_isolation": weak_isolation,
        "candidates": candidates,
        "repair_candidates": repair_candidates,
        "max_rounds": max_rounds,
    }
    if not (out / "run_manifest.json").exists():
        atomic_json(out / "run_manifest.json", manifest)

    state = read_json(out / "run_state.json", {
        "next_round": 0,
        "best_image": None,
        "best_candidate_id": None,
        "best_frozen_evaluation": None,
        "active_feedback": None,
        "online_memory": [],
        "no_improvement_rounds": 0,
    })
    state = _recover_committed_rounds(out, state)
    stop_reason = None

    while int(state["next_round"]) < max_rounds:
        round_index = int(state["next_round"])
        round_dir = out / "rounds" / f"round_{round_index:02d}"
        source_image = state.get("best_image")
        feedback = state.get("active_feedback")
        requested_count = candidates if round_index == 0 else repair_candidates
        generated, creator_record = creator.generate_candidates(
            ground_truth,
            round_dir,
            requested_count,
            feedback=feedback,
            source_image=source_image,
        )
        online_result = online_judge.evaluate(ground_truth, generated, memory=state.get("online_memory", []))
        selected_candidate, selected_online_eval = _selected(online_result, generated)
        frozen_result = frozen_judge.evaluate(ground_truth, [selected_candidate], memory=None)
        selected_frozen_eval = _single_frozen_evaluation(frozen_result)

        previous_best = state.get("best_frozen_evaluation")
        accepted = previous_best is None or _is_improvement(previous_best, selected_frozen_eval)
        critique_outcome = None
        repair_trajectory = None
        new_state = dict(state)
        if previous_best is None:
            accepted = True
        else:
            critique_outcome = _outcome(previous_best, selected_frozen_eval, feedback or {}, accepted, round_index)
            critique_outcome["ground_truth_hash"] = ground_truth_hash
            repair_trajectory = {
                "round": round_index,
                "ground_truth_hash": ground_truth_hash,
                "before_image": state.get("best_image"),
                "judge_feedback": feedback,
                "after_image": selected_candidate["path"],
                "accepted": accepted,
                "critique_outcome": critique_outcome,
            }
            new_state["online_memory"] = (list(state.get("online_memory", [])) + [critique_outcome])[-8:]

        if accepted:
            new_state.update({
                "best_image": selected_candidate["path"],
                "best_candidate_id": selected_candidate["candidate_id"],
                "best_frozen_evaluation": selected_frozen_eval,
                "active_feedback": selected_online_eval,
                "no_improvement_rounds": 0,
            })
        else:
            new_state["no_improvement_rounds"] = int(state.get("no_improvement_rounds", 0)) + 1
        new_state["next_round"] = round_index + 1

        summary = {
            "round": round_index,
            "source_image": source_image,
            "creator": creator_record,
            "candidates": generated,
            "online_judgement": online_result,
            "selected_candidate": selected_candidate,
            "selected_online_evaluation": selected_online_eval,
            "frozen_judgement": frozen_result,
            "selected_frozen_evaluation": selected_frozen_eval,
            "accepted_as_best": accepted,
            "preference_pairs": _preference_records(round_index, online_result, generated, ground_truth_hash),
            "repair_trajectory": repair_trajectory,
            "critique_outcome": critique_outcome,
            "state_after": new_state,
        }
        atomic_json(round_dir / "round_summary.json", summary)
        state = new_state
        atomic_json(out / "run_state.json", state)
        _rebuild_datasets(out)

        if _passes(state["best_frozen_evaluation"], ground_truth["thresholds"]):
            stop_reason = "thresholds_met"
            break
        if int(state.get("no_improvement_rounds", 0)) >= 2:
            stop_reason = "two_consecutive_rounds_without_improvement"
            break

    if stop_reason is None:
        stop_reason = "max_rounds_reached"
    if not state.get("best_image"):
        raise RuntimeError("Co-evolution completed without a usable image")

    approved_path = out / "approved_image.png"
    shutil.copyfile(state["best_image"], approved_path)
    thresholds_met = _passes(state["best_frozen_evaluation"], ground_truth["thresholds"])
    report = {
        "summary": "Creator Agent and Judge Model co-evolution completed.",
        "ok": True,
        "completed": True,
        "out_dir": str(out),
        "approved_image": str(approved_path),
        "thresholds_met": thresholds_met,
        "stop_reason": stop_reason,
        "rounds_completed": int(state["next_round"]),
        "best_frozen_evaluation": state["best_frozen_evaluation"],
        "online_judge_model": online_model,
        "frozen_judge_model": frozen_model,
        "weak_judge_isolation": weak_isolation,
        "warnings": ["Online and Frozen Judge use the same model; this is weak isolation and not suitable for formal conclusions."] if weak_isolation else [],
        "artifacts": {
            "preference_pairs": str(out / "preference_pairs.jsonl"),
            "repair_trajectories": str(out / "repair_trajectories.jsonl"),
            "critique_outcomes": str(out / "critique_outcomes.jsonl"),
            "run_manifest": str(out / "run_manifest.json"),
        },
    }
    atomic_json(out / "run_report.json", report)
    report["reproduction_metrics"] = analyze_coevolution_run(out)
    atomic_json(out / "run_report.json", report)
    return report
