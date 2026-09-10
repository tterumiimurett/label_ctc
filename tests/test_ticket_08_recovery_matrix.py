import json
import socket
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from prolific.ctc_verification_app.activation import ActionJournal, GuardedOutboundAdapter
from prolific.ctc_verification_app.contact_candidates import JsonContactLedger
from prolific.ctc_verification_app.outbound import send_approved_return_requests
from prolific.ctc_verification_app.reconciliation import ProlificSubmissionClient

class RecoveryMatrixTest(unittest.TestCase):
    def test_disconnect_after_message_post_is_unknown_and_never_resent_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            posts = []
            class Api(BaseHTTPRequestHandler):
                def do_GET(self):
                    body = json.dumps({"results": [{"id": "S1", "study_id": "STUDY", "participant": "P1", "status": "AWAITING REVIEW", "classification": "awaiting_without_final_result", "evidence": []}], "meta": {"count": 1}}).encode() if "submissions" in self.path else json.dumps({"id": "S1", "study_id": "STUDY", "participant": "P1", "status": "AWAITING REVIEW", "started_at": "2025-12-15T00:00:00Z"}).encode()
                    self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
                def do_POST(self):
                    posts.append(self.path); self.connection.shutdown(socket.SHUT_RDWR); self.connection.close()
                def log_message(self, *_args): pass
            server = ThreadingHTTPServer(("127.0.0.1", 0), Api); thread = threading.Thread(target=server.serve_forever); thread.start()
            try:
                client = ProlificSubmissionClient("local", f"http://127.0.0.1:{server.server_address[1]}/api/v1", retries=0)
                ledger_path = root / "contacts.json"; ledger = JsonContactLedger(ledger_path)
                ledger.write({"sessions": {"S1": {"state": "candidate", "candidate_origin": "new", "participant_id": "P1", "study_id": "STUDY", "first_missing_at": "2025-12-15T00:00:00+00:00"}}})
                report = {"status": "ok", "submissions": [{"session_id": "S1", "study_id": "STUDY", "participant_id": "P1", "status": "AWAITING REVIEW", "classification": "awaiting_without_final_result", "evidence": []}]}
                class Adapter:
                    def reconcile(self): return report
                    def inspect_messages(self, **_kwargs): return "clear"
                    def send_message(self, **kwargs): return client.send_message(**kwargs)
                first = send_approved_return_requests(report, ledger, Adapter(), approved_sessions={"S1"}, enabled=True)
                self.assertEqual(len(posts), 1); self.assertEqual(first["decisions"][0]["decision"], "delivery_unknown")
                second = send_approved_return_requests(report, JsonContactLedger(ledger_path), Adapter(), approved_sessions={"S1"}, enabled=True)
                self.assertEqual(len(posts), 1); self.assertEqual(second["decisions"][0]["decision"], "manual_review")
                self.assertEqual(second["decisions"][0]["reason"], "delivery_not_confirmed")
                self.assertEqual(JsonContactLedger(ledger_path).read()["sessions"]["S1"]["state"], "manual_review")
            finally:
                server.shutdown(); server.server_close(); thread.join()

    def test_disable_at_effect_boundary_blocks_subsequent_real_outbound_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); journal = ActionJournal(root / "actions.jsonl")
            entered = threading.Event(); release = threading.Event(); calls = []
            class Adapter:
                def send_message(self, **kwargs):
                    calls.append(kwargs); entered.set(); release.wait(2); return {"id": "M1"}
            guarded = GuardedOutboundAdapter(Adapter(), journal)
            first = threading.Thread(target=lambda: guarded.send_message(recipient_id="P1", body="x", study_id="STUDY"))
            first.start(); self.assertTrue(entered.wait(2)); journal.disable("operator stop"); release.set(); first.join(2)
            self.assertEqual(len(calls), 1); self.assertIsNone(journal.begin("recipient_message", {"recipient_id": "P2"}))

if __name__ == "__main__": unittest.main()
