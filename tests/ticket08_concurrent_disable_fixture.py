"""Controlled local-HTTP concurrent-disable integration fixture."""
import base64
import hashlib
import hmac
import json
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prolific.ctc_verification_app.activation import ActivationController, ActionJournal, Approval, ApprovalStore, RealApiAdapter, make_activation_server
from prolific.ctc_verification_app.app import VerificationStore
from prolific.ctc_verification_app.contact_candidates import JsonContactLedger, VerifiedMessageScope
from prolific.ctc_verification_app.reconciliation import ProlificSubmissionClient
from prolific.ctc_verification_app.triggers import JsonTriggerStore, ReconciliationTrigger
now = [datetime(2026, 9, 10, 12, tzinfo=timezone.utc)]
clock = lambda: now[0]
boundary = '2026-09-10T11:00:00Z'
states = {sid: {'id': sid, 'study_id': 'STUDY', 'participant': 'P' + sid, 'status': 'AWAITING REVIEW', 'started_at': '2026-09-10T11:50:00Z'} for sid in ['S1', 'S2', 'S3']}
states['S3']['status'] = 'ACTIVE'
posts = []
entered = threading.Event()
release = threading.Event()
gets = []

class API(BaseHTTPRequestHandler):

    def output(self, value):
        raw = json.dumps(value).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        gets.append(self.path)
        if self.path.startswith('/api/v1/messages/'):
            self.output({'results': [], '_links': {'self': {'href': self.path}}})
        elif self.path.startswith('/api/v1/submissions/?'):
            self.output({'results': list(states.values()), 'meta': {'count': 3}, '_links': {'self': {'href': self.path}}})
        else:
            self.output(states[self.path.rstrip('/').split('/')[-1]])

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        posts.append(body)
        if len(posts) == 1:
            entered.set()
            if not release.wait(15):
                self.send_error(500)
                return
        self.output({'id': 'M' + str(len(posts))})

    def log_message(self, *args):
        pass
api = ThreadingHTTPServer(('127.0.0.1', 0), API)
ta = threading.Thread(target=api.serve_forever)
ta.start()
receiver = None
tr = None
try:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        candidate = root / 'candidates.jsonl'
        candidate.write_text(json.dumps({'candidate_key': 'K', 'pred_is_ctc': True, 'audio_verify': {'verify_is_ctc': True}, 'tos_audio': {'outer_url': 'http://localhost/a.wav'}}) + '\n')
        store = VerificationStore([], [str(candidate)], root / 'data', 1, 3, 'https://example.test/complete', False)
        for sid in states:
            assert store.assign({'prolific_pid': 'P' + sid, 'study_id': 'STUDY', 'session_id': sid})['status'] == 'ok'
        scope = VerifiedMessageScope('R', 'W', now[0] - timedelta(days=1), now[0] + timedelta(days=1), True, 'complete controlled message API', now[0] - timedelta(minutes=1), now[0] + timedelta(days=1))
        approvals = ApprovalStore(root / 'approval.json')
        approvals.save(Approval(study_id='STUDY', preview_sha256='', sessions=('S3',), historical_sessions=(), routine_enabled=True, approved_at=now[0].isoformat(), approved_by='synthetic-reviewer'))

        def controller():
            client = ProlificSubmissionClient('synthetic-only', f'http://127.0.0.1:{api.server_port}/api/v1', retries=0)
            return ActivationController(trigger=ReconciliationTrigger(client, root / 'data', 'STUDY', JsonTriggerStore(root / 'events.json'), now=clock), store=VerificationStore([], [str(candidate)], root / 'data', 1, 3, 'https://example.test/complete', False), ledger=JsonContactLedger(root / 'contacts.json'), adapter=RealApiAdapter(client, root / 'data', 'STUDY', scope=scope, clock=clock), journal=ActionJournal(root / 'journal.jsonl'), study_id='STUDY', approvals=ApprovalStore(root / 'approval.json'), production_enabled=True, clock=clock, activation_boundary=boundary)
        c = controller()
        receiver = make_activation_server(c, 'secret', {'run_kind': 'event', 'activation_boundary': boundary})
        tr = threading.Thread(target=receiver.serve_forever)
        tr.start()

        def event(eid, sid):
            raw = json.dumps({'event_type': 'submission.status.change', 'resource_id': sid}).encode()
            ts = str(int(now[0].timestamp()))
            sig = base64.b64encode(hmac.new(b'secret', ts.encode() + raw, hashlib.sha256).digest()).decode()
            req = Request(f'http://127.0.0.1:{receiver.server_port}/', data=raw, headers={'X-Prolific-Request-Signature': sig, 'X-Prolific-Request-Timestamp': ts, 'X-Event-ID': eid, 'X-Timestamp': ts})
            with urlopen(req, timeout=10) as response:
                return json.loads(response.read())
        event('E1', 'S1')
        event('E2', 'S2')
        assert posts == []
        now[0] += timedelta(minutes=10)
        result = {}

        def run():
            try:
                result['scheduler'] = controller().scheduled_reassessment()
            except BaseException as exc:
                result['error'] = repr(exc)
        runner = threading.Thread(target=run)
        runner.start()
        assert entered.wait(10), 'No first HTTP POST reached controlled server'
        subprocess.run([sys.executable, '-c', "import sys;from pathlib import Path;sys.path.insert(0, '/tmp/prolific-round-d-20260910/ticket-08');from prolific.ctc_verification_app.activation import ActionJournal;ActionJournal(Path(sys.argv[1])).disable('independent process stop')", str(root / 'journal.jsonl')], check=True, timeout=10)
        release.set()
        runner.join(10)
        assert not runner.is_alive(), 'Deadlock after disable'
        assert 'error' not in result, result
        states['S3']['status'] = 'RETURNED'
        later = event('E3', 'S3')
        restart = controller().scheduled_reassessment()
        ledger = JsonContactLedger(root / 'contacts.json').read()
        assignments = json.loads(store.assignments_path.read_text())
        print(json.dumps({'POSTs': posts, 'ledger': ledger, 'later_lifecycle': later, 'restart': restart, 'S3_assignment_preserved': 'S3' in assignments, 'scheduler_error': result.get('error'), 'journal': (root / 'journal.jsonl').read_text()}, indent=2))
        assert len(posts) == 1, 'Second HTTP message POST occurred after disable'
        assert 'S3' in assignments, 'Lifecycle effect occurred after disable'
finally:
    release.set()
    if receiver:
        receiver.shutdown()
        receiver.server_close()
        tr.join()
    api.shutdown()
    api.server_close()
    ta.join()
