import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from rfs.coevolution.groundtruth import load_ground_truth
from rfs.coevolution.orchestrator import run_image_coevolution


class FakeProvider:
    def __init__(self, supports_edit=False, fail_edit=False, fail_after=None):
        self._supports_edit = supports_edit
        self.fail_edit = fail_edit
        self.fail_after = fail_after
        self.calls = []

    @property
    def supports_edit(self):
        return self._supports_edit

    def _write(self, output_path, color):
        Image.new("RGB", (96, 54), color).save(output_path)

    def _maybe_fail(self):
        if self.fail_after is not None and len(self.calls) >= self.fail_after:
            raise RuntimeError("simulated provider failure")

    def generate(self, prompt, output_path, aspect_ratio):
        self._maybe_fail()
        self.calls.append({"mode": "generate", "prompt": prompt, "path": str(output_path)})
        self._write(output_path, (30 + len(self.calls) * 15, 120, 180))
        return {"mode": "generate", "model": "fake-image"}

    def edit(self, source_path, prompt, output_path, aspect_ratio):
        self._maybe_fail()
        self.calls.append({"mode": "edit", "prompt": prompt, "path": str(output_path), "source": str(source_path)})
        if self.fail_edit:
            raise RuntimeError("simulated edit failure")
        self._write(output_path, (180, 80 + len(self.calls) * 10, 90))
        return {"mode": "edit", "model": "fake-edit"}


class FakeJudge:
    def __init__(self, model_name, scores, feedback=True, secret=None):
        self.model_name = model_name
        self.scores = list(scores)
        self.feedback = feedback
        self.secret = secret
        self.calls = []

    def evaluate(self, ground_truth, candidates, memory=None):
        call_index = len(self.calls)
        score_spec = self.scores[min(call_index, len(self.scores) - 1)]
        self.calls.append({"candidates": [item["candidate_id"] for item in candidates], "memory": memory})
        evaluations = []
        for index, candidate in enumerate(candidates):
            if isinstance(score_spec, dict):
                total = float(score_spec.get("total", 0.7)) - index * 0.02
                scientific = float(score_spec.get("scientific", total)) - index * 0.01
                aesthetic = float(score_spec.get("aesthetic", total)) - index * 0.01
                visual = float(score_spec.get("visual", total)) - index * 0.01
                blockers = list(score_spec.get("blocking", []))
            else:
                total = float(score_spec) - index * 0.02
                scientific = aesthetic = visual = total
                blockers = []
            evaluations.append({
                "candidate_id": candidate["candidate_id"],
                "scientific_score": scientific,
                "aesthetic_score": aesthetic,
                "visual_quality_score": visual,
                "total_score": total,
                "blocking_issues": blockers,
                "preserve": ["keep the blue input area"] if self.feedback else [],
                "repair": [{
                    "region": "center",
                    "problem": "weak hierarchy",
                    "ground_truth_basis": "aesthetic preference requests strong hierarchy",
                    "instruction": "enlarge the core method and use a restrained orange accent",
                }] if self.feedback else [],
                "confidence": 0.9,
                "summary": self.secret or "fake judgement",
            })
        ranking = [item["candidate_id"] for item in sorted(evaluations, key=lambda item: item["total_score"], reverse=True)]
        return {"ranking": ranking, "evaluations": evaluations, "model": self.model_name, "summary": self.secret or "fake"}


def make_ground_truth(root: Path, **overrides) -> Path:
    paper = root / "paper.txt"
    paper.write_text("A paper about a feature encoder and reasoning module.", encoding="utf-8")
    data = {
        "paper_path": "paper.txt",
        "scientific_truth": {
            "figure_goal": "Explain the method.",
            "must_show": ["feature encoder", "reasoning module"],
            "relations": [{"source": "feature encoder", "target": "reasoning module"}],
            "must_not_invent": ["external database"],
        },
        "aesthetic_preferences": {"description": "Academic, blue and teal, dense but readable."},
        "thresholds": {"total": 0.85, "scientific": 0.9, "aesthetic": 0.8},
    }
    data.update(overrides)
    path = root / "ground_truth.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class GroundTruthTests(unittest.TestCase):
    def test_missing_and_contradictory_ground_truth_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(FileNotFoundError):
                load_ground_truth(root / "missing.json")

            path = make_ground_truth(root, scientific_truth={
                "must_show": ["database"],
                "must_not_invent": ["database"],
            })
            with self.assertRaisesRegex(ValueError, "contradict"):
                load_ground_truth(path)


class CoevolutionTests(unittest.TestCase):
    def test_initial_generation_edit_repair_training_outputs_and_completed_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gt = make_ground_truth(root)
            out = root / "run"
            provider = FakeProvider(supports_edit=True)
            online = FakeJudge("online-model", [0.70, 0.88], feedback=True)
            frozen = FakeJudge("frozen-model", [
                {"total": 0.70, "scientific": 0.92, "aesthetic": 0.65, "visual": 0.72},
                {"total": 0.90, "scientific": 0.96, "aesthetic": 0.86, "visual": 0.90},
            ], feedback=False, secret="FROZEN_SECRET")

            result = run_image_coevolution(gt, out, provider=provider, online_judge=online, frozen_judge=frozen)

            self.assertTrue(result["thresholds_met"])
            self.assertEqual(result["stop_reason"], "thresholds_met")
            self.assertEqual(result["rounds_completed"], 2)
            self.assertEqual([call["mode"] for call in provider.calls], ["generate", "generate", "generate", "edit", "edit"])
            repair_prompt = (out / "rounds" / "round_01" / "candidate_01_prompt.txt").read_text(encoding="utf-8")
            self.assertIn("keep the blue input area", repair_prompt)
            self.assertIn("enlarge the core method", repair_prompt)
            self.assertNotIn("FROZEN_SECRET", repair_prompt)
            self.assertTrue((out / "approved_image.png").exists())
            self.assertTrue((out / "reproduction_metrics.json").exists())
            metrics = json.loads((out / "reproduction_metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(metrics["rounds_committed"], 2)
            self.assertEqual(metrics["candidates_generated"], 5)
            self.assertEqual(metrics["feedback_effective_rounds"], 1)
            self.assertEqual(metrics["repair_requests"], 1)
            self.assertAlmostEqual(metrics["score_gains"]["total_score"], 0.2)
            self.assertTrue(metrics["independent_acceptance_configured"])
            self.assertEqual(len((out / "preference_pairs.jsonl").read_text(encoding="utf-8").splitlines()), 3)
            self.assertEqual(len((out / "repair_trajectories.jsonl").read_text(encoding="utf-8").splitlines()), 1)
            outcome = json.loads((out / "critique_outcomes.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertTrue(outcome["feedback_effective"])
            self.assertTrue(online.calls[1]["memory"] == [])

            no_call_provider = FakeProvider(fail_after=0)
            resumed = run_image_coevolution(gt, out, provider=no_call_provider, online_judge=online, frozen_judge=frozen)
            self.assertEqual(resumed, result)
            self.assertEqual(no_call_provider.calls, [])
            with self.assertRaisesRegex(ValueError, "different Ground Truth or co-evolution configuration"):
                run_image_coevolution(gt, out, candidates=4, provider=no_call_provider, online_judge=online, frozen_judge=frozen)

    def test_edit_failure_falls_back_to_complete_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gt = make_ground_truth(root)
            out = root / "run"
            provider = FakeProvider(supports_edit=True, fail_edit=True)
            online = FakeJudge("online", [0.60, 0.65])
            frozen = FakeJudge("frozen", [0.60, 0.65], feedback=False)

            result = run_image_coevolution(
                gt, out, candidates=1, repair_candidates=1, max_rounds=2,
                provider=provider, online_judge=online, frozen_judge=frozen,
            )

            self.assertEqual(result["stop_reason"], "max_rounds_reached")
            summary = json.loads((out / "rounds" / "round_01" / "round_summary.json").read_text(encoding="utf-8"))
            generation = summary["candidates"][0]["generation"]
            self.assertEqual(generation["mode"], "generate_fallback")
            self.assertIn("simulated edit failure", generation["edit_fallback_error"])
            self.assertEqual([call["mode"] for call in provider.calls], ["generate", "edit", "generate"])

    def test_regressions_roll_back_and_stop_after_two_no_improvement_rounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gt = make_ground_truth(root)
            out = root / "run"
            provider = FakeProvider(supports_edit=False)
            online = FakeJudge("online", [0.70, 0.75, 0.78])
            frozen = FakeJudge("frozen", [0.70, 0.60, 0.65], feedback=False)

            result = run_image_coevolution(
                gt, out, candidates=1, repair_candidates=1, max_rounds=4,
                provider=provider, online_judge=online, frozen_judge=frozen,
            )

            self.assertEqual(result["stop_reason"], "two_consecutive_rounds_without_improvement")
            self.assertEqual(result["rounds_completed"], 3)
            initial = (out / "rounds" / "round_00" / "candidate_01.png").read_bytes()
            self.assertEqual((out / "approved_image.png").read_bytes(), initial)
            outcomes = [json.loads(line) for line in (out / "critique_outcomes.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([item["accepted_as_best"] for item in outcomes], [False, False])
            self.assertEqual(len(online.calls[2]["memory"]), 1)

    def test_interrupted_run_resumes_after_last_committed_round(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gt = make_ground_truth(root)
            out = root / "run"
            failing = FakeProvider(supports_edit=False, fail_after=1)
            online1 = FakeJudge("online", [0.60])
            frozen1 = FakeJudge("frozen", [0.60], feedback=False)

            with self.assertRaisesRegex(RuntimeError, "All image candidates failed"):
                run_image_coevolution(
                    gt, out, candidates=1, repair_candidates=1, max_rounds=2,
                    provider=failing, online_judge=online1, frozen_judge=frozen1,
                )
            initial_bytes = (out / "rounds" / "round_00" / "candidate_01.png").read_bytes()

            provider = FakeProvider(supports_edit=False)
            online2 = FakeJudge("online", [0.70])
            frozen2 = FakeJudge("frozen", [0.90], feedback=False)
            result = run_image_coevolution(
                gt, out, candidates=1, repair_candidates=1, max_rounds=2,
                provider=provider, online_judge=online2, frozen_judge=frozen2,
            )

            self.assertEqual(result["rounds_completed"], 2)
            self.assertEqual(len(provider.calls), 1)
            self.assertEqual((out / "rounds" / "round_00" / "candidate_01.png").read_bytes(), initial_bytes)

    def test_uncommitted_existing_candidate_is_reused_after_judge_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gt = make_ground_truth(root)
            out = root / "run"
            provider = FakeProvider()

            class FailingJudge(FakeJudge):
                def evaluate(self, ground_truth, candidates, memory=None):
                    raise RuntimeError("simulated judge failure")

            with self.assertRaisesRegex(RuntimeError, "simulated judge failure"):
                run_image_coevolution(
                    gt, out, candidates=1, max_rounds=1, provider=provider,
                    online_judge=FailingJudge("online", [0.5]),
                    frozen_judge=FakeJudge("frozen", [0.5], feedback=False),
                )
            self.assertEqual(len(provider.calls), 1)

            second_provider = FakeProvider(fail_after=0)
            result = run_image_coevolution(
                gt, out, candidates=1, max_rounds=1, provider=second_provider,
                online_judge=FakeJudge("online", [0.9]),
                frozen_judge=FakeJudge("frozen", [0.9], feedback=False),
            )
            self.assertEqual(second_provider.calls, [])
            self.assertEqual(result["rounds_completed"], 1)

    def test_all_initial_provider_failures_leave_no_approved_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gt = make_ground_truth(root)
            out = root / "run"
            provider = FakeProvider(fail_after=0)
            with self.assertRaisesRegex(RuntimeError, "All image candidates failed"):
                run_image_coevolution(
                    gt, out, candidates=2, provider=provider,
                    online_judge=FakeJudge("online", [0.5]),
                    frozen_judge=FakeJudge("frozen", [0.5], feedback=False),
                )
            self.assertFalse((out / "approved_image.png").exists())


if __name__ == "__main__":
    unittest.main()
