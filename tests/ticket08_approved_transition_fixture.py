"""Pinned fd8bac6 real HTTP positive-path acceptance attempt; localhost/temp only."""
import base64, hashlib, hmac, json, sys, tempfile, threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prolific.ctc_verification_app.activation import ActivationController, ActionJournal, Approval, ApprovalStore, RealApiAdapter, make_activation_server
from prolific.ctc_verification_app.app import VerificationStore
from prolific.ctc_verification_app.contact_candidates import JsonContactLedger, VerifiedMessageScope, build_contact_candidates
from prolific.ctc_verification_app.reconciliation import ProlificSubmissionClient
from prolific.ctc_verification_app.triggers import JsonTriggerStore, ReconciliationTrigger
now = [datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)]
clock = lambda: now[0]
boundary = '2026-09-10T11:00:00Z'
state = {'id': 'S1', 'study_id': 'STUDY', 'participant': 'P1', 'status': 'AWAITING REVIEW', 'started_at': '2026-09-10T11:50:00Z', 'entered_code': 'NOCODE'}
posts = []
gets = []

class API(BaseHTTPRequestHandler):

    def output(self, data):
        raw = json.dumps(data).encode()
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
            self.output({'results': [state], 'meta': {'count': 1}, '_links': {'self': {'href': self.path}}})
        elif self.path.startswith('/api/v1/submissions/S1'):
            self.output(state)
        else:
            self.send_error(404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        posts.append({'path': self.path, 'body': body})
        self.output({'id': 'M1'})

    def log_message(self, *a):
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
        candidate.write_text(json.dumps({'candidate_key': 'V00_S0001_I00000001|P1|P2|11.000|21.000|target', 'pred_is_ctc': True, 'audio_verify': {'verify_is_ctc': True}, 'tos_audio': {'outer_url': 'http://127.0.0.1/seamless_ctc_V00_S0001_I00000001_001100_002100.wav'}}) + '\n', encoding='utf-8')
        store = VerificationStore([], [str(candidate)], root / 'data', 1, 1, 'https://example.test/complete', False)
        assert store.assign({'prolific_pid': 'P1', 'study_id': 'STUDY', 'session_id': 'S1'})['status'] == 'ok'
        client = ProlificSubmissionClient('synthetic-only', f'http://127.0.0.1:{api.server_port}/api/v1', retries=0)
        trigger = ReconciliationTrigger(client, root / 'data', 'STUDY', JsonTriggerStore(root / 'events.json'), now=clock)
        scope = VerifiedMessageScope('R', 'W', now[0] - timedelta(days=1), now[0] + timedelta(days=1), True, 'controlled API all message pages visible', now[0] - timedelta(minutes=1), now[0] + timedelta(days=1))
        adapter = RealApiAdapter(client, root / 'data', 'STUDY', scope=scope, clock=clock)
        approvals = ApprovalStore(root / 'approval.json')
        approvals.save(Approval(study_id='STUDY', preview_sha256='', sessions=(), historical_sessions=(), routine_enabled=True, approved_at=now[0].isoformat(), approved_by='synthetic-reviewer'))
        ledger = JsonContactLedger(root / 'contacts.json')
        c = ActivationController(trigger=trigger, store=store, ledger=ledger, adapter=adapter, journal=ActionJournal(root / 'journal.jsonl'), study_id='STUDY', approvals=approvals, production_enabled=True, clock=clock, activation_boundary=boundary)
        receiver = make_activation_server(c, 'synthetic-secret', {'run_kind': 'event', 'activation_boundary': boundary})
        tr = threading.Thread(target=receiver.serve_forever)
        tr.start()

        def event(eid):
            raw = json.dumps({'event_type': 'submission.status.change', 'resource_id': 'S1'}).encode()
            ts = str(int(now[0].timestamp()))
            sig = base64.b64encode(hmac.new(b'synthetic-secret', ts.encode() + raw, hashlib.sha256).digest()).decode()
            request = Request(f'http://127.0.0.1:{receiver.server_port}/', data=raw, headers={'Content-Type': 'application/json', 'X-Prolific-Request-Signature': sig, 'X-Prolific-Request-Timestamp': ts, 'X-Event-ID': eid, 'X-Timestamp': ts})
            with urlopen(request) as response:
                return json.loads(response.read())
        mode = sys.argv[1] if len(sys.argv) > 1 else 'positive'
        def submit_answer(target_store=store):
            worker = {'prolific_pid': 'P1', 'study_id': 'STUDY', 'session_id': 'S1'}
            assignment = target_store.assign(worker)
            payload = {'schema_version': 'ctc-verification-v1', 'worker': worker, 'assignment': assignment['assignment'], 'tasks': [{'candidate_id': t['candidate_id'], 'task_id': t['task_id'], 'relevant_interruption': False} for t in assignment['tasks']]}
            submit_result = target_store.submit(payload)
            assert submit_result['status'] == 'ok', submit_result
        if mode == 'initial_answer':
            submit_answer()
        first = event('E1')
        if mode in {'answer', 'answer5'}:
            before_answer = ledger.read()
            assert before_answer['sessions']['S1'].get('first_missing_at'), 'First missing observation was not durable before answer'
            if mode == 'answer5':
                now[0] += timedelta(minutes=5)
            submit_answer()
        if mode == 'approved':
            state['status'] = 'APPROVED'
        if mode != 'answer5':
            now[0] += timedelta(minutes=10)
        store2 = VerificationStore([], [str(candidate)], root / 'data', 1, 1, 'https://example.test/complete', False)
        trigger2 = ReconciliationTrigger(client, root / 'data', 'STUDY', JsonTriggerStore(root / 'events.json'), now=clock)
        ledger2 = JsonContactLedger(root / 'contacts.json')
        adapter2 = RealApiAdapter(client, root / 'data', 'STUDY', scope=scope, clock=clock)
        c2 = ActivationController(trigger=trigger2, store=store2, ledger=ledger2, adapter=adapter2, journal=ActionJournal(root / 'journal.jsonl'), study_id='STUDY', approvals=ApprovalStore(root / 'approval.json'), production_enabled=True, clock=clock, activation_boundary=boundary)

        def build_reconstructed_stack():
            rebuilt_store = VerificationStore([], [str(candidate)], root / 'data', 1, 1, 'https://example.test/complete', False)
            rebuilt_client = ProlificSubmissionClient('synthetic-only', f'http://127.0.0.1:{api.server_port}/api/v1', retries=0)
            rebuilt_trigger = ReconciliationTrigger(rebuilt_client, root / 'data', 'STUDY', JsonTriggerStore(root / 'events.json'), now=clock)
            rebuilt_ledger = JsonContactLedger(root / 'contacts.json')
            rebuilt_adapter = RealApiAdapter(rebuilt_client, root / 'data', 'STUDY', scope=scope, clock=clock)
            rebuilt_controller = ActivationController(trigger=rebuilt_trigger, store=rebuilt_store, ledger=rebuilt_ledger, adapter=rebuilt_adapter, journal=ActionJournal(root / 'journal.jsonl'), study_id='STUDY', approvals=ApprovalStore(root / 'approval.json'), production_enabled=True, clock=clock, activation_boundary=boundary)
            return rebuilt_controller, rebuilt_ledger

        outer_report = None
        if mode == 'fresh_only':
            outer_report = json.loads((root / 'events.json').read_text(encoding='utf-8'))['events']['E1']['report']
            assert outer_report and outer_report.get('submissions') and outer_report['submissions'][0]['classification'] == 'awaiting_without_final_result', outer_report
            class FreshArrivalBarrier:
                def __init__(self):
                    self.submitted = False
                    self.last_report = None

                def reconcile(self):
                    if not self.submitted:
                        submit_answer(store2)
                        self.submitted = True
                    self.last_report = adapter2.reconcile()
                    return self.last_report

                def inspect_messages(self, **kwargs):
                    return adapter2.inspect_messages(**kwargs)

            barrier = FreshArrivalBarrier()
            second = build_contact_candidates(outer_report, ledger2, barrier, candidate_origin='new', now=now[0])
            assert barrier.last_report['submissions'][0]['classification'] == 'matched'
            assert ledger2.read()['sessions']['S1']['state'] == 'resolved'
            rebuilt_controller, rebuilt_ledger = build_reconstructed_stack()
            followup = rebuilt_controller.scheduled_reassessment()
            followup_ledger = rebuilt_ledger.read()
        else:
            second = c2.scheduled_reassessment()
            if mode == 'positive':
                assert ledger2.read()['sessions']['S1']['state'] == 'sent', 'Positive approved candidate did not record accepted send'
            elif mode == 'approved':
                assert ledger2.read()['sessions']['S1']['state'] == 'manual_review', 'Approved status did not remain manual'
            else:
                assert ledger2.read()['sessions']['S1']['state'] == 'resolved', 'Complete answer did not resolve before reconstructed follow-up'
            rebuilt_controller, rebuilt_ledger = build_reconstructed_stack()
            followup = rebuilt_controller.scheduled_reassessment()
            followup_ledger = rebuilt_ledger.read()
        print(json.dumps({'mode': mode, 'first': first, 'outer_report': outer_report, 'elapsed_minutes': 5 if mode == 'answer5' else 10, 'after_reassessment': second, 'followup': followup, 'ledger': followup_ledger if 'followup_ledger' in locals() else ledger.read(), 'message_GETs': [p for p in gets if '/messages/' in p], 'POSTs': posts}, indent=2))
        assert len(posts) == (1 if mode == 'positive' else 0), 'Unexpected POST count'
        if mode == 'positive':
            assert followup_ledger['sessions']['S1']['state'] == 'manual_review', 'Accepted send follow-up did not require manual confirmation'
            assert followup_ledger['sessions']['S1']['send_attempt_count'] == 1, 'Positive follow-up changed attempt count'
        if mode == 'approved':
            assert followup_ledger['sessions']['S1']['state'] == 'manual_review', 'Missing durable manual disposition'
        if mode in {'answer', 'answer5', 'initial_answer', 'fresh_only'}:
            assert followup_ledger['sessions']['S1']['state'] == 'resolved', 'Complete answer did not resolve waiting case'
        if mode == 'fresh_only':
            assert not second.get('decisions'), 'Fresh answer created an unexpected candidate/manual decision'
            assert all(not session.get('candidates', {}).get('decisions') and not session.get('outbound', {}).get('decisions') for session in followup.get('sessions', [])), 'Reconstructed fresh answer reassessment created a decision'
finally:
    if receiver:
        receiver.shutdown()
        receiver.server_close()
        tr.join()
    api.shutdown()
    api.server_close()
    ta.join()
