import tempfile
import unittest
import json
from unittest.mock import patch
from pathlib import Path
from prolific.ctc_verification_app.contact_candidates import APPROVED_MESSAGE, JsonContactLedger
from prolific.ctc_verification_app.outbound import send_approved_return_requests
from prolific.ctc_verification_app.contact_candidates import build_contact_candidates
from prolific.ctc_verification_app.reconciliation import ProlificSubmissionClient
from prolific.ctc_verification_app.contact_candidates import ProlificFreshReconciliation

def report():
    return {"status":"ok","study_id":"STUDY","submissions":[{"session_id":"S1","study_id":"STUDY","participant_id":"P1","status":"AWAITING REVIEW","classification":"awaiting_without_final_result"}]}
class Adapter:
    def __init__(self, history="clear", error=None): self.history=history; self.error=error; self.sent=[]
    def reconcile(self): return report()
    def inspect_messages(self, **kwargs): return self.history
    def send_message(self, **kwargs):
        self.sent.append(kwargs)
        if self.error: raise self.error
        return {"id":"M1"}
class Ticket06OutboundTest(unittest.TestCase):
    def test_fresh_reconciliation_composes_with_real_client_send(self):
        class Reader:
            def send_message(self, **kwargs): return {"id": "M2", "echo": kwargs}
        adapter=ProlificFreshReconciliation(Reader(), Path("/tmp"), "STUDY")
        self.assertEqual(adapter.send_message(recipient_id="P1", body="approved", study_id="STUDY")["id"], "M2")

    def test_real_adapter_posts_one_documented_message_operation(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'{"id":"M1"}'
        calls=[]
        class Opener:
            def open(self, request, timeout): calls.append((request, timeout)); return Response()
        with patch("prolific.ctc_verification_app.reconciliation.build_opener", return_value=Opener()):
            client=ProlificSubmissionClient("synthetic", "https://api.test/v1")
            result=client.send_message(recipient_id="P1", body="approved", study_id="STUDY")
        request=calls[0][0]
        self.assertEqual(request.method, "POST"); self.assertTrue(request.full_url.endswith("/messages/"))
        self.assertEqual(json.loads(request.data), {"recipient_id":"P1","body":"approved","study_id":"STUDY"})
        self.assertEqual(result["id"], "M1")
    def test_new_candidates_auto_execute_but_legacy_candidates_need_history_approval(self):
        with tempfile.TemporaryDirectory() as d:
            ledger=JsonContactLedger(Path(d)/"c.json")
            ledger.write({"sessions":{"NEW":{"state":"candidate","candidate_origin":"new","study_id":"STUDY","participant_id":"P1"}, "OLD":{"state":"candidate","study_id":"STUDY","participant_id":"P2"}}})
            class CaseAdapter(Adapter):
                def __init__(self, value): super().__init__(); self.value=value
                def reconcile(self): return self.value
            adapter=CaseAdapter({"status":"ok","study_id":"STUDY","submissions":[{"session_id":"NEW","study_id":"STUDY","participant_id":"P1","status":"AWAITING REVIEW","classification":"awaiting_without_final_result"}]})
            value=report()
            result=send_approved_return_requests(value, ledger, adapter, enabled=True)
            self.assertEqual(result["decisions"][0]["decision"], "sent"); self.assertEqual(len(adapter.sent), 1)
            adapter2=Adapter(); old_ledger=JsonContactLedger(Path(d)/"old.json")
            old_ledger.write({"sessions":{"OLD":{"state":"candidate","study_id":"STUDY","participant_id":"P2"}}})
            value["submissions"][0]["session_id"]="OLD"; value["submissions"][0]["participant_id"]="P2"
            result=send_approved_return_requests(value, old_ledger, adapter2, enabled=True)
            self.assertEqual(result["decisions"][0]["reason"], "historical_candidate_requires_explicit_approval"); self.assertEqual(adapter2.sent, [])

    def test_ordered_chat_rules(self):
        from datetime import datetime, timezone
        from prolific.ctc_verification_app.contact_candidates import ProlificFreshReconciliation, VerifiedMessageScope
        scope=VerifiedMessageScope("R", "W", datetime(2026,8,5,tzinfo=timezone.utc), datetime(2026,9,1,tzinfo=timezone.utc), True, "verified", datetime(2026,8,31,tzinfo=timezone.utc), datetime(2026,9,2,tzinfo=timezone.utc))
        class Reader:
            def __init__(self, messages): self.messages=messages
            def get_submission(self, sid): return {"study_id":"STUDY","participant":"P1","started_at":"2026-08-15T00:00:00Z"}
            def get_messages(self, **kwargs): return {"results":self.messages}
        def adapter(messages): return ProlificFreshReconciliation(Reader(messages), Path("/tmp"), "STUDY", scope=scope, now=datetime(2026,9,1,tzinfo=timezone.utc))
        self.assertEqual(adapter([]).inspect_messages(session_id="S1",participant_id="P1",study_id="STUDY"), "clear")
        old=[{"sender_id":"R","created_at":"2026-08-20T00:00:00Z","body":"hello"}]
        self.assertEqual(adapter(old).inspect_messages(session_id="S1",participant_id="P1",study_id="STUDY"), "clear")
        newer=[*old,{"sender_id":"P1","created_at":"2026-08-21T00:00:00Z","body":"I completed"}]
        self.assertEqual(adapter(newer).inspect_messages(session_id="S1",participant_id="P1",study_id="STUDY"), "participant_reply")
        unknown=[{"sender_id":"R","created_at":"2026-08-20T00:00:00Z","body":"hello"},{"sender_id":"OTHER","created_at":"2026-08-21T00:00:00Z","body":"?"}]
        self.assertEqual(adapter(unknown).inspect_messages(session_id="S1",participant_id="P1",study_id="STUDY"), "ambiguous")
        tied=[{"sender_id":"R","created_at":"2026-08-20T00:00:00Z","body":"hello"},{"sender_id":"P1","created_at":"2026-08-20T00:00:00Z","body":"?"}]
        self.assertEqual(adapter(tied).inspect_messages(session_id="S1",participant_id="P1",study_id="STUDY"), "ambiguous")
        only_participant=[{"sender_id":"P1","created_at":"2026-08-20T00:00:00Z","body":"help"}]
        prior=[{"sender_id":"R","created_at":"2026-08-20T00:00:00Z","body":"Please return this submission"}]
        class ReturnedReader:
            def get_submission(self, sid): return {"study_id":"STUDY","participant":"P1","started_at":"2026-08-15T00:00:00Z","return_requested":True}
            def get_messages(self, **kwargs): return {"results": []}
        self.assertEqual(ProlificFreshReconciliation(ReturnedReader(), Path("/tmp"), "STUDY", scope=scope, now=datetime(2026,9,1,tzinfo=timezone.utc)).inspect_messages(session_id="S1",participant_id="P1",study_id="STUDY"), "prior_contact")
        self.assertEqual(adapter(prior).inspect_messages(session_id="S1",participant_id="P1",study_id="STUDY"), "prior_contact")
        self.assertEqual(adapter(only_participant).inspect_messages(session_id="S1",participant_id="P1",study_id="STUDY"), "participant_reply")

    def test_disabled_by_default_and_requires_candidate_approval(self):
        ledger=JsonContactLedger(Path(tempfile.mkdtemp())/"c.json")
        adapter=Adapter()
        self.assertEqual(send_approved_return_requests(report(), ledger, adapter, approved_sessions={"S1"})["status"], "disabled")
        self.assertEqual(send_approved_return_requests(report(), ledger, adapter, approved_sessions={"S1"}, enabled=True)["decisions"][0]["decision"], "manual_review")
        self.assertEqual(adapter.sent, [])
    def test_persists_intent_before_single_send_and_does_not_return(self):
        with tempfile.TemporaryDirectory() as d:
            ledger=JsonContactLedger(Path(d)/"c.json"); ledger.write({"sessions":{"S1":{"state":"candidate","study_id":"STUDY","participant_id":"P1"}}})
            adapter=Adapter(); result=send_approved_return_requests(report(), ledger, adapter, approved_sessions={"S1"}, enabled=True)
            self.assertEqual(result["decisions"][0]["decision"], "sent"); self.assertEqual(len(adapter.sent),1)
            self.assertEqual(adapter.sent[0]["body"], APPROVED_MESSAGE.format(SESSION_ID="S1"))
            saved=ledger.read()["sessions"]["S1"]; self.assertEqual(saved["state"],"sent"); self.assertTrue(saved["return_status_unchanged"])
    def test_candidate_builder_and_outbound_share_timeout_attempt_barrier(self):
        with tempfile.TemporaryDirectory() as d:
            ledger_path=Path(d)/"c.json"; ledger=JsonContactLedger(ledger_path)
            ledger.write({"sessions":{"S1":{"state":"candidate","study_id":"STUDY","participant_id":"P1"}}})
            adapter=Adapter(error=TimeoutError("timeout"))
            first=send_approved_return_requests(report(), ledger, adapter, approved_sessions={"S1"}, enabled=True)
            self.assertEqual(first["decisions"][0]["decision"], "delivery_unknown")
            build=build_contact_candidates(report(), JsonContactLedger(ledger_path), adapter, candidate_origin="new", now="2026-09-09T00:10:00Z")
            self.assertEqual(JsonContactLedger(ledger_path).read()["sessions"]["S1"]["state"], "delivery_unknown")
            adapter.error=None; second=send_approved_return_requests(report(), JsonContactLedger(ledger_path), adapter, approved_sessions={"S1"}, enabled=True)
            self.assertEqual(second["decisions"][0]["decision"], "delivery_unknown"); self.assertEqual(len(adapter.sent), 1)

    def test_successful_send_remains_protected_if_state_is_mutated(self):
        with tempfile.TemporaryDirectory() as d:
            ledger_path=Path(d)/"c.json"; ledger=JsonContactLedger(ledger_path)
            ledger.write({"sessions":{"S1":{"state":"candidate","study_id":"STUDY","participant_id":"P1"}}})
            adapter=Adapter(); send_approved_return_requests(report(), ledger, adapter, approved_sessions={"S1"}, enabled=True)
            value=ledger.read(); value["sessions"]["S1"]["state"]="candidate"; ledger.write(value)
            result=send_approved_return_requests(report(), ledger, adapter, approved_sessions={"S1"}, enabled=True)
            self.assertEqual(result["decisions"][0]["decision"], "sent"); self.assertEqual(len(adapter.sent), 1)

    def test_latest_reconciliation_cancels_after_result_arrives(self):
        with tempfile.TemporaryDirectory() as d:
            ledger=JsonContactLedger(Path(d)/"c.json"); ledger.write({"sessions":{"S1":{"state":"candidate","study_id":"STUDY","participant_id":"P1"}}})
            class Arrives(Adapter):
                def __init__(self): super().__init__(); self.calls=0
                def reconcile(self):
                    self.calls += 1
                    value=report()
                    if self.calls > 1: value["submissions"][0]["classification"]="matched"
                    return value
            adapter=Arrives(); result=send_approved_return_requests(report(), ledger, adapter, approved_sessions={"S1"}, enabled=True)
            self.assertEqual(result["decisions"][0]["decision"], "manual_review"); self.assertEqual(adapter.sent, [])

    def test_timeout_is_unknown_and_never_retried(self):
        with tempfile.TemporaryDirectory() as d:
            ledger=JsonContactLedger(Path(d)/"c.json"); ledger.write({"sessions":{"S1":{"state":"candidate","study_id":"STUDY","participant_id":"P1"}}})
            adapter=Adapter(error=TimeoutError("timeout")); result=send_approved_return_requests(report(), ledger, adapter, approved_sessions={"S1"}, enabled=True)
            self.assertEqual(result["decisions"][0]["decision"], "delivery_unknown"); self.assertEqual(len(adapter.sent),1)
            self.assertEqual(ledger.read()["sessions"]["S1"]["state"], "delivery_unknown")
    def test_latest_draft_and_return_requested_block_without_send(self):
        for evidence in ("draft", "archived_result", "other_session_result"):
            with self.subTest(evidence=evidence), tempfile.TemporaryDirectory() as d:
                ledger=JsonContactLedger(Path(d)/"c.json"); ledger.write({"sessions":{"S1":{"state":"candidate","study_id":"STUDY","participant_id":"P1"}}})
                adapter=Adapter(); adapter.reconcile=lambda: {**report(), "submissions":[{**report()["submissions"][0], "evidence":[evidence]}]}
                result=send_approved_return_requests(report(), ledger, adapter, approved_sessions={"S1"}, enabled=True)
                self.assertEqual(result["decisions"][0]["decision"], "manual_review"); self.assertEqual(adapter.sent, [])

    def test_original_identity_mismatch_blocks_new_participant(self):
        with tempfile.TemporaryDirectory() as d:
            ledger=JsonContactLedger(Path(d)/"c.json"); ledger.write({"sessions":{"S1":{"state":"candidate","study_id":"STUDY","participant_id":"P1"}}})
            adapter=Adapter(); adapter.reconcile=lambda: {**report(), "submissions":[{**report()["submissions"][0], "participant_id":"P9"}]}
            result=send_approved_return_requests(report(), ledger, adapter, approved_sessions={"S1"}, enabled=True)
            self.assertEqual(result["decisions"][0]["decision"], "manual_review"); self.assertEqual(adapter.sent, [])

    def test_concurrent_process_like_calls_send_at_most_once(self):
        import threading
        with tempfile.TemporaryDirectory() as d:
            ledger_path=Path(d)/"c.json"; JsonContactLedger(ledger_path).write({"sessions":{"S1":{"state":"candidate","study_id":"STUDY","participant_id":"P1"}}})
            class SlowAdapter(Adapter):
                def send_message(self, **kwargs):
                    self.sent.append(kwargs); threading.Event().wait(0.03); return {"id":"M1"}
            adapters=[SlowAdapter(), SlowAdapter()]; results=[]
            def run(adapter): results.append(send_approved_return_requests(report(), JsonContactLedger(ledger_path), adapter, approved_sessions={"S1"}, enabled=True))
            threads=[threading.Thread(target=run,args=(adapter,)) for adapter in adapters]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            self.assertEqual(sum(len(adapter.sent) for adapter in adapters), 1)
            self.assertEqual(sorted(result["decisions"][0]["decision"] for result in results), ["sent", "sent"])

    def test_restart_reconciles_sending_and_unknown_without_send(self):
        with tempfile.TemporaryDirectory() as d:
            ledger=JsonContactLedger(Path(d)/"c.json"); ledger.write({"sessions":{"S1":{"state":"sending","study_id":"STUDY","participant_id":"P1"}}})
            adapter=Adapter(history="clear"); result=send_approved_return_requests(report(), ledger, adapter, enabled=True)
            self.assertEqual(result["decisions"][0]["decision"], "delivery_unknown"); self.assertEqual(adapter.sent, [])
            ledger.write({"sessions":{"S1":{"state":"delivery_unknown","study_id":"STUDY","participant_id":"P1"}}}); adapter.history="prior_contact"
            result=send_approved_return_requests(report(), ledger, adapter, approved_sessions={"S1"}, enabled=True)
            self.assertEqual(result["decisions"][0]["decision"], "manual_review"); self.assertEqual(adapter.sent, [])

    def test_malformed_success_response_is_not_sent(self):
        with tempfile.TemporaryDirectory() as d:
            ledger=JsonContactLedger(Path(d)/"c.json"); ledger.write({"sessions":{"S1":{"state":"candidate","study_id":"STUDY","participant_id":"P1"}}})
            adapter=Adapter(); adapter.send_message=lambda **kwargs: {}
            result=send_approved_return_requests(report(), ledger, adapter, approved_sessions={"S1"}, enabled=True)
            self.assertEqual(result["decisions"][0]["decision"], "delivery_unknown"); self.assertEqual(ledger.read()["sessions"]["S1"]["state"], "delivery_unknown")

    def test_fresh_state_change_cancels_without_send(self):
        with tempfile.TemporaryDirectory() as d:
            ledger=JsonContactLedger(Path(d)/"c.json"); ledger.write({"sessions":{"S1":{"state":"candidate","study_id":"STUDY","participant_id":"P1"}}})
            adapter=Adapter(); adapter.reconcile=lambda: {**report(), "submissions":[{**report()["submissions"][0],"classification":"matched"}]}
            result=send_approved_return_requests(report(), ledger, adapter, approved_sessions={"S1"}, enabled=True)
            self.assertEqual(result["decisions"][0]["decision"], "manual_review"); self.assertEqual(adapter.sent, [])
if __name__ == "__main__": unittest.main()
