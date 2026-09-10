import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unittest.mock import Mock

from prolific.ctc_verification_app.activation import ActionJournal, ActivationController, Approval, ApprovalStore
from prolific.ctc_verification_app.app import VerificationStore
from prolific.ctc_verification_app.contact_candidates import JsonContactLedger

def run(mode: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        candidate = root / "candidates.jsonl"
        candidate.write_text(json.dumps({"candidate_key": "K", "pred_is_ctc": True, "audio_verify": {"verify_is_ctc": True}, "tos_audio": {"outer_url": "http://localhost/a.wav"}}) + "\n", encoding="utf-8")
        store = VerificationStore([], [str(candidate)], root / "data", 1, 1, "https://example.test", False)
        store.assign({"prolific_pid": "P", "study_id": "STUDY", "session_id": "S"})
        before = (root / "data" / "assignments.json").read_bytes()
        row = {"session_id": "S", "study_id": "STUDY", "participant_id": "P", "status": "RETURNED", "classification": "returned_without_local_result", "proposed_action": "release_claim_proposal"}
        report = {"status": "ok", "study_id": "STUDY", "submissions": [row]}
        fresh = dict(row)
        if mode == "wrong_study":
            fresh.update(study_id="WRONG", classification="identity_mismatch", proposed_action="manual_review")
        elif mode == "read_error":
            fresh.update(errors=["simulated read error"], classification="local_read_error", proposed_action="manual_review")
        elif mode == "consent":
            fresh["consent_withdrawn"] = True
        adapter = Mock()
        adapter.reconcile.return_value = {**report, "submissions": [fresh]}
        approvals = ApprovalStore(root / "approval.json")
        approvals.save(Approval("STUDY", "", (), (), (), mode != "default_off", "fixture", "test"))
        controller = ActivationController(trigger=Mock(), store=store, ledger=JsonContactLedger(root / "contacts.json"), adapter=adapter, journal=ActionJournal(root / "actions.jsonl"), study_id="STUDY", approvals=approvals if mode != "default_off" else None, production_enabled=mode != "default_off")
        result = controller.execute(provenance_context={}, report=report)
        after = (root / "data" / "assignments.json").read_bytes()
        return {"mode": mode, "result": result, "unchanged": before == after, "remaining": "S" in json.loads(after)}

if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1]), sort_keys=True))
