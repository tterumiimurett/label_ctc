import base64
import hashlib
import hmac
import json
import socket
import tempfile
import threading
import unittest
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from prolific.ctc_verification_app.activation import (
    ActionJournal, ActivationController, Approval, ApprovalStore,
    RealApiAdapter, make_activation_server,
)
from prolific.ctc_verification_app.app import VerificationStore
from prolific.ctc_verification_app.contact_candidates import JsonContactLedger, VerifiedMessageScope
from prolific.ctc_verification_app.reconciliation import ProlificSubmissionClient
from prolific.ctc_verification_app.triggers import JsonTriggerStore, ReconciliationTrigger


class AuthenticRecoveryTest(unittest.TestCase):
    def test_scheduler_restart_after_disconnect_is_single_post_and_manual(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            now = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
            posts = []
            platform = {
                "id": "S1", "study_id": "STUDY", "participant": "P1",
                "status": "AWAITING REVIEW", "started_at": "2026-01-01T00:00:00Z",
            }

            class ControlledApi(BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path.startswith("/api/v1/messages/"):
                        value = {"results": [], "_links": {"self": {"href": self.path}}}
                    elif "?" in self.path:
                        value = {"results": [platform], "meta": {"count": 1}, "_links": {"self": {"href": self.path}}}
                    else:
                        value = platform
                    raw = json.dumps(value).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)

                def do_POST(self):
                    length = int(self.headers.get("Content-Length", "0"))
                    posts.append(json.loads(self.rfile.read(length).decode("utf-8")))
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()

                def log_message(self, *_args):
                    pass

            api = ThreadingHTTPServer(("127.0.0.1", 0), ControlledApi)
            api_thread = threading.Thread(target=api.serve_forever)
            api_thread.start()
            receiver = None
            receiver_thread = None
            try:
                candidate = root / "candidates.jsonl"
                candidate.write_text(json.dumps({
                    "candidate_key": "K", "pred_is_ctc": True,
                    "audio_verify": {"verify_is_ctc": True},
                    "tos_audio": {"outer_url": "http://localhost/audio.wav"},
                }) + "\n", encoding="utf-8")
                store = VerificationStore([], [str(candidate)], root / "data", 1, 1, "https://example.test/complete", False)
                self.assertEqual(store.assign({"prolific_pid": "P1", "study_id": "STUDY", "session_id": "S1"})["status"], "ok")
                base_url = "http://127.0.0.1:%d/api/v1" % api.server_address[1]
                scope = VerifiedMessageScope(
                    "RESEARCHER", "WORKSPACE", now[0] - timedelta(days=1), now[0] + timedelta(days=1),
                    True, "controlled complete message visibility", now[0], now[0] + timedelta(days=1),
                )
                approvals = ApprovalStore(root / "approval.json")
                approvals.save(Approval("STUDY", "", (), (), (), True, now[0].isoformat(), "fixture"))

                def build():
                    client = ProlificSubmissionClient("local", base_url, retries=0)
                    trigger = ReconciliationTrigger(client, root / "data", "STUDY", JsonTriggerStore(root / "events.json"), now=lambda: now[0])
                    adapter = RealApiAdapter(client, root / "data", "STUDY", scope=scope, clock=lambda: now[0])
                    return ActivationController(
                        trigger=trigger, store=VerificationStore([], [str(candidate)], root / "data", 1, 1, "https://example.test/complete", False),
                        ledger=JsonContactLedger(root / "contacts.json"), adapter=adapter,
                        journal=ActionJournal(root / "journal.jsonl"), study_id="STUDY", approvals=approvals,
                        production_enabled=True, clock=lambda: now[0], activation_boundary="1970-01-01T00:00:00Z",
                    )

                controller = build()
                receiver = make_activation_server(controller, "secret", {"run_kind": "event", "activation_boundary": "1970-01-01T00:00:00Z", "study_id": "STUDY"})
                receiver_thread = threading.Thread(target=receiver.serve_forever)
                receiver_thread.start()
                body = json.dumps({"event_type": "submission.status.change", "resource_id": "S1"}).encode()
                timestamp = str(int(now[0].timestamp()))
                signature = base64.b64encode(hmac.new(b"secret", timestamp.encode() + body, hashlib.sha256).digest()).decode()
                request = urllib.request.Request(
                    "http://127.0.0.1:%d/" % receiver.server_address[1], data=body, method="POST",
                    headers={"X-Prolific-Request-Signature": signature, "X-Prolific-Request-Timestamp": timestamp, "X-Event-ID": "E1", "X-Timestamp": timestamp},
                )
                urllib.request.urlopen(request).read()
                now[0] += timedelta(seconds=600)
                first = controller.scheduled_reassessment()
                self.assertEqual(len(posts), 1)
                self.assertEqual(first["sessions"][0]["outbound"]["decisions"][0]["decision"], "delivery_unknown")
                receiver.shutdown()
                receiver.server_close()
                receiver_thread.join()
                reconstructed = build()
                second = reconstructed.scheduled_reassessment()
                self.assertEqual(len(posts), 1)
                self.assertEqual(second["sessions"][0]["outbound"]["decisions"][0]["decision"], "manual_review")
                self.assertEqual(JsonContactLedger(root / "contacts.json").read()["sessions"]["S1"]["state"], "manual_review")
                self.assertEqual(JsonContactLedger(root / "contacts.json").read()["sessions"]["S1"]["send_outcome"], "unknown")
            finally:
                if receiver is not None:
                    receiver.shutdown()
                    receiver.server_close()
                if receiver_thread is not None:
                    receiver_thread.join()
                api.shutdown()
                api.server_close()
                api_thread.join()


if __name__ == "__main__":
    unittest.main()
