"""Sanitized regressions for explicit sole-member personal message scope."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from prolific.ctc_verification_app.contact_candidates import ProlificFreshReconciliation, VerifiedMessageScope
from prolific.ctc_verification_app.activation_cli import _verified_scope


class PersonalReader:
    def __init__(self, messages=None, members=None, current=None, error=None):
        self.messages = messages if messages is not None else []
        self.members = members if members is not None else [{"id": "RESEARCHER"}]
        self.current = current if current is not None else {"id": "RESEARCHER"}
        self.error = error
        self.calls = []

    def get_submission(self, session_id):
        return {"id": session_id, "study_id": "STUDY", "participant": "P1", "started_at": "2026-09-01T00:00:00Z"}

    def get_current_user(self):
        if self.error:
            raise self.error
        self.calls.append("users/me")
        return self.current

    def list_workspace_members(self, workspace_id):
        if self.error:
            raise self.error
        self.calls.append(f"members:{workspace_id}")
        return {"results": self.members}

    def get_messages(self, **kwargs):
        if self.error:
            raise self.error
        self.calls.append(kwargs)
        return {"results": self.messages, "_links": {"self": {"href": "controlled"}}}


def personal_scope(**overrides):
    values = {
        "researcher_id": "RESEARCHER", "workspace_id": "WORKSPACE",
        "coverage_start": datetime(2026, 8, 15, tzinfo=timezone.utc),
        "coverage_end": datetime(2026, 9, 10, tzinfo=timezone.utc),
        "workspace_visibility_verified": False, "verification_note": "sole-member personal proof",
        "checked_at": datetime(2026, 9, 9, tzinfo=timezone.utc),
        "expires_at": datetime(2026, 9, 10, 23, tzinfo=timezone.utc),
        "mode": "personal", "personal_proof": {"sole_member_id": "RESEARCHER", "proof_kind": "current_users_me_and_workspace_members"},
    }
    values.update(overrides)
    return VerifiedMessageScope(**values)


class PersonalMessageScopeTest(unittest.TestCase):
    now = datetime(2026, 9, 10, tzinfo=timezone.utc)

    def inspect(self, reader, scope=None):
        adapter = ProlificFreshReconciliation(reader, Path("/tmp/controlled"), "STUDY", scope=scope or personal_scope(), now=self.now)
        return adapter.inspect_messages(session_id="S1", participant_id="P1", study_id="STUDY")

    def test_personal_scope_reads_datetime_created_and_omits_workspace_query(self):
        reader = PersonalReader([
            {"sender_id": "RESEARCHER", "datetime_created": "2026-09-09T00:00:00Z", "body": "status update"},
            {"sender_id": "P1", "sent_at": "2026-09-09T01:00:00Z", "body": "I completed"},
        ])
        self.assertEqual(self.inspect(reader), "participant_reply")
        self.assertEqual(reader.calls[-1], {"user_id": "P1", "created_after": "2026-08-15T00:00:00Z"})
        self.assertFalse(personal_scope().workspace_visibility_verified)

    def test_personal_scope_known_return_request_is_manual(self):
        reader = PersonalReader([{
            "sender_id": "RESEARCHER", "datetime_created": "2026-09-09T00:00:00Z",
            "body": "Please return this submission",
        }])
        self.assertEqual(self.inspect(reader), "prior_contact")

    def test_personal_scope_empty_complete_history_is_clear(self):
        self.assertEqual(self.inspect(PersonalReader([])), "clear")

    def test_personal_scope_rejects_invalid_or_conflicting_timestamps(self):
        invalid = PersonalReader([{"sender_id": "RESEARCHER", "datetime_created": "not-a-date", "body": "x"}])
        conflict = PersonalReader([{"sender_id": "RESEARCHER", "datetime_created": "2026-09-09T00:00:00Z", "created_at": "2026-09-09T00:01:00Z", "body": "x"}])
        self.assertEqual(self.inspect(invalid), "unavailable")
        self.assertEqual(self.inspect(conflict), "unavailable")

    def test_personal_scope_fails_closed_on_membership_or_permission_change(self):
        self.assertEqual(self.inspect(PersonalReader(members=[{"id": "RESEARCHER"}, {"id": "OTHER"}])), "unavailable")
        self.assertEqual(self.inspect(PersonalReader(current={"id": "OTHER"})), "unavailable")
        self.assertEqual(self.inspect(PersonalReader(error=PermissionError("forbidden"))), "unavailable")

    def test_cli_requires_explicit_personal_proof_and_keeps_workspace_mode(self):
        raw = {
            "mode": "personal", "researcher_id": "RESEARCHER", "workspace_id": "WORKSPACE",
            "coverage_start": "2026-08-05T00:00:00Z", "coverage_end": "2026-09-10T00:00:00Z",
            "workspace_visibility_verified": True, "verification_note": "personal proof",
            "checked_at": "2026-09-09T00:00:00Z", "expires_at": "2026-09-10T23:00:00Z",
            "personal_proof": {"sole_member_id": "RESEARCHER"},
        }
        scope = _verified_scope({"message_scope": raw})
        self.assertEqual(scope.mode, "personal")
        self.assertFalse(scope.workspace_visibility_verified)
        raw.pop("personal_proof")
        with self.assertRaises(ValueError):
            _verified_scope({"message_scope": raw})


if __name__ == "__main__":
    unittest.main()
