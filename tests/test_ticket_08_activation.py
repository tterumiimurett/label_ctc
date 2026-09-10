import json
import tempfile
import unittest
from pathlib import Path

from prolific.ctc_verification_app.activation import ActionLog, ActivationController


class Ticket08ActivationTest(unittest.TestCase):
    def report(self):
        return {"status": "ok", "writes_performed": False, "submissions": [
            {"session_id": "S1", "study_id": "STUDY", "participant_id": "P1",
             "status": "RETURNED", "proposed_action": "archived_result", "evidence": ["final_result"]}
        ]}

    def test_preview_is_read_only_and_requires_all_identity_permission_gates(self):
        with tempfile.TemporaryDirectory() as d:
            log = ActionLog(Path(d) / "actions.jsonl")
            controller = ActivationController(reader=object(), study_id="STUDY", action_log=log)
            result = controller.preview(self.report())
            self.assertFalse(result["activation_allowed"])
            self.assertFalse(list(Path(d).glob("*.disabled")))
            self.assertEqual(len(list(Path(d).glob("actions.jsonl"))), 1)

    def test_controlled_execution_is_durable_and_can_be_disabled(self):
        with tempfile.TemporaryDirectory() as d:
            log = ActionLog(Path(d) / "actions.jsonl")
            controller = ActivationController(reader=object(), study_id="STUDY", workspace_id="W",
                                               permissions_verified=True, identity_verified=True, action_log=log)
            seen = []
            result = controller.execute(self.report(), archive=lambda row: seen.append(row) or {"status": "archived"})
            self.assertEqual(result["status"], "ok")
            self.assertEqual(seen[0]["session_id"], "S1")
            log.disable("human gate closed")
            blocked = controller.execute(self.report(), archive=lambda row: self.fail("must not run"))
            self.assertEqual(blocked["status"], "blocked")
            events = [json.loads(line) for line in Path(d, "actions.jsonl").read_text().splitlines()]
            self.assertIn("action_completed", [event["kind"] for event in events])
            self.assertIn("future_actions_disabled", [event["kind"] for event in events])

    def test_production_execution_never_runs(self):
        with tempfile.TemporaryDirectory() as d:
            controller = ActivationController(reader=object(), study_id="STUDY", action_log=ActionLog(Path(d, "a")), production=True)
            with self.assertRaises(PermissionError):
                controller.execute(self.report())

    def test_candidate_origin_is_required(self):
        with tempfile.TemporaryDirectory() as d:
            controller = ActivationController(reader=object(), study_id="STUDY", workspace_id="W",
                                               permissions_verified=True, identity_verified=True, action_log=ActionLog(Path(d, "a")))
            with self.assertRaises(ValueError):
                controller.execute({"status": "ok", "writes_performed": False, "submissions": []}, candidates=lambda **_: {})


if __name__ == "__main__":
    unittest.main()
