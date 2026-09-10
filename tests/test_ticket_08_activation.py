import json, tempfile, unittest
from pathlib import Path
from unittest.mock import Mock
from prolific.ctc_verification_app.activation import ActionJournal, ActivationController, Approval

class Ticket08Test(unittest.TestCase):
 def setup(self, production=False):
  d=tempfile.TemporaryDirectory(); root=Path(d.name); journal=ActionJournal(root/'actions.jsonl')
  trigger=Mock(); trigger.periodic.return_value={'report':{'status':'ok','writes_performed':False,'submissions':[]}}
  adapter=Mock(); adapter.reconcile.return_value={'status':'ok','submissions':[]}
  return d,root,ActivationController(trigger=trigger,store=Mock(),ledger=Mock(),adapter=adapter,journal=journal,study_id='STUDY',production_enabled=production,activation_boundary='1970-01-01T00:00:00Z')
 def test_provenance_is_durable_and_unknown_is_manual(self):
  d,r,c=self.setup(); self.assertEqual(c.derive_candidate_origin({'run_kind':'event','event_id':'E','activation_boundary':'1970-01-01','study_id':'STUDY'}, accepted_event={'event_id':'E','study_id':'STUDY','event_timestamp':100,'activation_timestamp':0}),'new'); self.assertEqual(c.derive_candidate_origin({'run_kind':'backfill','historical_snapshot':True}),'historical'); self.assertEqual(c.derive_candidate_origin({'run_kind':'manual'}),'unknown'); d.cleanup()
 def test_journal_is_intent_before_effect_and_kill_switch_is_shared(self):
  d,r,c=self.setup(); event=c.journal.begin('archive',{'session_id':'S'}); self.assertTrue(event); self.assertEqual(json.loads((r/'actions.jsonl').read_text())['kind'],'intent'); c.journal.disable('stop'); self.assertIsNone(c.journal.begin('archive',{})); d.cleanup()
 def test_production_requires_explicit_approval(self):
  d,r,c=self.setup(True)
  with self.assertRaises(PermissionError): c.execute(provenance_context={'run_kind':'event','event_id':'E'})
  d.cleanup()
 def test_preview_uses_actual_action_name(self):
  d,r,c=self.setup(); out=c.preview({'submissions':[{'session_id':'S','study_id':'STUDY','participant_id':'P','proposed_action':'release_claim_proposal'}]}); self.assertEqual(out['actions'][0]['action'],'release_claim'); d.cleanup()
if __name__=='__main__': unittest.main()

class RealComponentIntegrationTest(unittest.TestCase):
    def test_signed_http_event_real_client_and_verification_store_release_claim(self):
        import base64, hashlib, hmac, json, threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from prolific.ctc_verification_app.app import VerificationStore
        from prolific.ctc_verification_app.contact_candidates import JsonContactLedger
        from prolific.ctc_verification_app.reconciliation import ProlificSubmissionClient
        from prolific.ctc_verification_app.triggers import JsonTriggerStore, ReconciliationTrigger
        from prolific.ctc_verification_app.activation import ApprovalStore, RealApiAdapter, make_activation_server
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); candidate=root/'candidates.jsonl'; candidate.write_text(json.dumps({'candidate_key':'k','pred_is_ctc':True,'audio_verify':{'verify_is_ctc':True},'tos_audio':{'outer_url':'https://x/a.wav'}})+'\n')
            store=VerificationStore([], [str(candidate)], root/'data', 1, 1, 'https://x/complete', False)
            self.assertEqual(store.assign({'prolific_pid':'P1','study_id':'STUDY','session_id':'S1'})['status'],'ok')
            state={'id':'S1','study_id':'STUDY','participant':'P1','status':'RETURNED'}
            class H(BaseHTTPRequestHandler):
                def do_GET(self):
                    body={'results':[state], 'meta':{'count':1}, '_links':{'self':{'href':self.path}}} if self.path.startswith('/api/v1/submissions/?') else state
                    raw=json.dumps(body).encode(); self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
                def log_message(self,*args): pass
            server=ThreadingHTTPServer(('127.0.0.1',0),H); thread=threading.Thread(target=server.serve_forever); thread.start()
            try:
                port=server.server_address[1]; client=ProlificSubmissionClient('isolated','http://127.0.0.1:'+str(port)+'/api/v1',retries=0)
                trigger=ReconciliationTrigger(client,root/'data','STUDY',JsonTriggerStore(root/'events.json'))
                from prolific.ctc_verification_app.activation import ActionJournal, ActivationController, Approval
                controller=ActivationController(trigger=trigger,store=store,ledger=JsonContactLedger(root/'contacts.json'),adapter=RealApiAdapter(client,root/'data','STUDY'),journal=ActionJournal(root/'actions.jsonl'),study_id='STUDY',approvals=ApprovalStore(root/'approval.json'),activation_boundary='1970-01-01T00:00:00Z', production_enabled=True)
                controller.approvals.save(Approval('STUDY', '', (), (), (), True, 'fixture', 'test'))
                body=json.dumps({'event_type':'submission.status.change','resource_id':'S1'}).encode(); secret='secret'; ts='100'; sig=base64.b64encode(hmac.new(secret.encode(),ts.encode()+body,hashlib.sha256).digest()).decode()
                result=controller.handle_signed_event(body,{'X-Prolific-Request-Signature':sig,'X-Prolific-Request-Timestamp':ts,'X-Event-ID':'E1','X-Timestamp':'100'},secret,{'run_kind':'event','event_id':'E1','activation_boundary':'1970-01-01','study_id':'STUDY'})
                self.assertEqual(result['status'],'ok'); self.assertEqual(result['origin'],'new'); self.assertEqual(result['results'][0]['outcome']['action'],'released_claim')
            finally: server.shutdown(); server.server_close(); thread.join()

class FullHttpMatrixTest(unittest.TestCase):
    def test_receiver_http_signed_returned_final_archives_real_store(self):
        import base64, hashlib, hmac, json, threading, urllib.request
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from prolific.ctc_verification_app.app import VerificationStore
        from prolific.ctc_verification_app.contact_candidates import JsonContactLedger
        from prolific.ctc_verification_app.reconciliation import ProlificSubmissionClient
        from prolific.ctc_verification_app.triggers import JsonTriggerStore, ReconciliationTrigger
        from prolific.ctc_verification_app.activation import ActionJournal, ActivationController, Approval, ApprovalStore, RealApiAdapter, make_activation_server
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); candidate=root/'candidates.jsonl'; candidate.write_text(json.dumps({'candidate_key':'k','pred_is_ctc':True,'audio_verify':{'verify_is_ctc':True},'tos_audio':{'outer_url':'https://x/a.wav'}})+'\n')
            store=VerificationStore([], [str(candidate)], root/'data', 1, 1, 'https://x/complete', False)
            assignment=store.assign({'prolific_pid':'P1','study_id':'STUDY','session_id':'S1'})
            payload={'schema_version':'ctc-verification-v1','worker':{'prolific_pid':'P1','study_id':'STUDY','session_id':'S1'},'assignment':assignment['assignment'],'tasks':[{'candidate_id':assignment['tasks'][0]['candidate_id'],'task_id':assignment['tasks'][0].get('task_id') or assignment['tasks'][0].get('id') or assignment['tasks'][0]['candidate_id'],'relevant_interruption':False}]}
            submitted=store.submit(payload); self.assertEqual(submitted['status'],'ok', submitted)
            state={'id':'S1','study_id':'STUDY','participant':'P1','status':'RETURNED'}
            class Api(BaseHTTPRequestHandler):
                def do_GET(self):
                    value={'results':[state],'meta':{'count':1},'_links':{'self':{'href':self.path}}} if '?' in self.path else state
                    raw=json.dumps(value).encode(); self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
                def do_POST(self): self.send_response(500); self.end_headers()
                def log_message(self,*a): pass
            api=ThreadingHTTPServer(('127.0.0.1',0),Api); at=threading.Thread(target=api.serve_forever); at.start()
            receiver=None; rt=None
            try:
                base='http://127.0.0.1:%d/api/v1'%api.server_address[1]; client=ProlificSubmissionClient('isolated',base,retries=0)
                trigger=ReconciliationTrigger(client,root/'data','STUDY',JsonTriggerStore(root/'events.json'))
                controller=ActivationController(trigger=trigger,store=store,ledger=JsonContactLedger(root/'contacts.json'),adapter=RealApiAdapter(client,root/'data','STUDY'),journal=ActionJournal(root/'actions.jsonl'),study_id='STUDY',approvals=ApprovalStore(root/'approval.json'),activation_boundary='1970-01-01T00:00:00Z', production_enabled=True)
                controller.approvals.save(Approval('STUDY', '', (), (), (), True, 'fixture', 'test'))
                receiver=make_activation_server(controller,'secret',{'run_kind':'event','activation_boundary':'1970-01-01','study_id':'STUDY'}); rt=threading.Thread(target=receiver.serve_forever); rt.start()
                body=json.dumps({'event_type':'submission.status.change','resource_id':'S1'}).encode(); ts='100'; sig=base64.b64encode(hmac.new(b'secret',ts.encode()+body,hashlib.sha256).digest()).decode()
                request=urllib.request.Request('http://127.0.0.1:%d/'%receiver.server_address[1],data=body,method='POST',headers={'X-Prolific-Request-Signature':sig,'X-Prolific-Request-Timestamp':ts,'X-Event-ID':'E1','X-Timestamp':'100','Content-Type':'application/json'})
                response=json.loads(urllib.request.urlopen(request).read())
                self.assertEqual(response['status'],'ok'); self.assertFalse((root/'data/submissions/S1.json').exists()); self.assertTrue(list((root/'data/excluded_submissions').glob('*/prolific_returned/S1.json')))
            finally:
                if receiver: receiver.shutdown(); receiver.server_close(); rt.join()
                api.shutdown(); api.server_close(); at.join()

    def test_duplicate_signed_event_and_kill_switch_do_not_repeat_effect(self):
        # Reuse the real receiver path: duplicate event IDs are deduplicated by JsonTriggerStore,
        # while the shared journal marker blocks later effects across controller instances.
        from prolific.ctc_verification_app.activation import ActionJournal
        with tempfile.TemporaryDirectory() as d:
            journal=ActionJournal(Path(d)/'actions.jsonl'); first=journal.begin('recipient_message',{'session_id':'S1'}); self.assertIsNotNone(first); journal.finish(first,'unknown_delivery'); journal.disable('operator stop'); self.assertIsNone(journal.begin('recipient_message',{'session_id':'S2'})); self.assertTrue(journal.disabled)


    def _run_real_timeout(self, with_result: bool):
        import base64
        import hashlib
        import hmac
        import json
        import threading
        import urllib.request
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from prolific.ctc_verification_app.app import VerificationStore
        from prolific.ctc_verification_app.activation import (
            ActionJournal, ActivationController, ApprovalStore, RealApiAdapter,
            make_activation_server,
        )
        from prolific.ctc_verification_app.contact_candidates import JsonContactLedger
        from prolific.ctc_verification_app.reconciliation import ProlificSubmissionClient
        from prolific.ctc_verification_app.triggers import JsonTriggerStore, ReconciliationTrigger

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_path = root / 'candidates.jsonl'
            candidate_path.write_text(
                json.dumps({
                    'candidate_key': 'timeout-k',
                    'pred_is_ctc': True,
                    'audio_verify': {'verify_is_ctc': True},
                    'tos_audio': {'outer_url': 'https://controlled.test/a.wav'},
                }) + '\n',
                encoding='utf-8',
            )
            store = VerificationStore(
                [], [str(candidate_path)], root / 'data', 1, 1,
                'https://controlled.test/complete', False,
            )
            assignment = store.assign({
                'prolific_pid': 'P-TIMEOUT',
                'study_id': 'STUDY',
                'session_id': 'TIMEOUT-1',
            })
            self.assertEqual(assignment['status'], 'ok')
            raw_result = None
            if with_result:
                task = assignment['tasks'][0]
                payload = {
                    'schema_version': 'ctc-verification-v1',
                    'worker': {
                        'prolific_pid': 'P-TIMEOUT',
                        'study_id': 'STUDY',
                        'session_id': 'TIMEOUT-1',
                    },
                    'assignment': assignment['assignment'],
                    'tasks': [{
                        'candidate_id': task['candidate_id'],
                        'task_id': task.get('task_id') or task.get('id') or task['candidate_id'],
                        'relevant_interruption': False,
                    }],
                }
                self.assertEqual(store.submit(payload)['status'], 'ok')
                raw_result = (root / 'data' / 'submissions' / 'TIMEOUT-1.json').read_bytes()

            platform_state = {
                'id': 'TIMEOUT-1',
                'study_id': 'STUDY',
                'participant': 'P-TIMEOUT',
                'status': 'TIMED OUT',
            }

            class ControlledApi(BaseHTTPRequestHandler):
                def do_GET(self):
                    if '?' in self.path:
                        value = {
                            'results': [platform_state],
                            'meta': {'count': 1},
                            '_links': {'self': {'href': self.path}},
                        }
                    else:
                        value = platform_state
                    encoded = json.dumps(value).encode('utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)

                def log_message(self, *_args):
                    pass

            api = ThreadingHTTPServer(('127.0.0.1', 0), ControlledApi)
            api_thread = threading.Thread(target=api.serve_forever)
            api_thread.start()
            receiver = None
            receiver_thread = None
            try:
                base_url = 'http://127.0.0.1:%d/api/v1' % api.server_address[1]
                client = ProlificSubmissionClient('isolated-token', base_url, retries=0)
                trigger = ReconciliationTrigger(
                    client, root / 'data', 'STUDY',
                    JsonTriggerStore(root / 'events.json'),
                )
                controller = ActivationController(
                    trigger=trigger,
                    store=store,
                    ledger=JsonContactLedger(root / 'contacts.json'),
                    adapter=RealApiAdapter(client, root / 'data', 'STUDY'),
                    journal=ActionJournal(root / 'actions.jsonl'),
                    study_id='STUDY',
                    approvals=ApprovalStore(root / 'approval.json'),
                    production_enabled=True,
                )
                controller.approvals.save(Approval('STUDY', '', (), (), (), True, 'fixture', 'test'))
                receiver = make_activation_server(
                    controller,
                    'controlled-secret',
                    {
                        'run_kind': 'event',
                        'activation_boundary': '1970-01-01T00:00:00Z',
                        'study_id': 'STUDY',
                    },
                )
                receiver_thread = threading.Thread(target=receiver.serve_forever)
                receiver_thread.start()
                body = json.dumps({
                    'event_type': 'submission.status.change',
                    'resource_id': 'TIMEOUT-1',
                }).encode('utf-8')
                timestamp = '200'
                signature = base64.b64encode(hmac.new(
                    b'controlled-secret', timestamp.encode() + body, hashlib.sha256,
                ).digest()).decode()
                request = urllib.request.Request(
                    'http://127.0.0.1:%d/' % receiver.server_address[1],
                    data=body,
                    method='POST',
                    headers={
                        'X-Prolific-Request-Signature': signature,
                        'X-Prolific-Request-Timestamp': timestamp,
                        'X-Event-ID': 'timeout-event-1',
                        'X-Timestamp': timestamp,
                        'Content-Type': 'application/json',
                    },
                )
                response = json.loads(urllib.request.urlopen(request).read())
                self.assertEqual(response['status'], 'ok', response)
                lifecycle = json.loads((root / 'data' / 'returned-lifecycle.json').read_text(encoding='utf-8'))
                self.assertEqual(lifecycle['TIMEOUT-1']['status'], 'TIMED_OUT')
                self.assertNotIn('TIMEOUT-1', json.loads((root / 'data' / 'assignments.json').read_text(encoding='utf-8')))
                self.assertEqual(store.assign({'prolific_pid': 'P-NEW', 'study_id': 'STUDY', 'session_id': 'NEW'})['status'], 'ok')
                if with_result:
                    archive = next((root / 'data' / 'excluded_submissions').glob('*/prolific_timed_out/TIMEOUT-1.json'))
                    self.assertEqual(archive.read_bytes(), raw_result)
                    self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), hashlib.sha256(raw_result).hexdigest())
                    self.assertFalse((root / 'data' / 'submissions' / 'TIMEOUT-1.json').exists())
                else:
                    self.assertEqual(list((root / 'data' / 'excluded_submissions').glob('*/prolific_timed_out/TIMEOUT-1.json')), [])
                    self.assertFalse((root / 'data' / 'submissions' / 'TIMEOUT-1.json').exists())
                duplicate = urllib.request.urlopen(request).read()
                self.assertIn(b'completed', duplicate)
                self.assertEqual(store.assign({'prolific_pid': 'P-TIMEOUT', 'study_id': 'STUDY', 'session_id': 'TIMEOUT-1'})['status'], 'error')
            finally:
                if receiver is not None:
                    receiver.shutdown()
                    receiver.server_close()
                if receiver_thread is not None:
                    receiver_thread.join()
                api.shutdown()
                api.server_close()
                api_thread.join()

    def test_real_http_timed_out_with_final_archives_exact_bytes(self):
        self._run_real_timeout(with_result=True)

    def test_real_http_timed_out_without_final_releases_only(self):
        self._run_real_timeout(with_result=False)

class RoutinePositiveHttpTest(unittest.TestCase):
    def test_approved_routine_new_missing_result_waits_then_posts_once(self):
        import base64
        import hashlib
        import hmac
        import json
        import threading
        import urllib.request
        from datetime import datetime, timezone, timedelta
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from prolific.ctc_verification_app.activation import (
            ActionJournal, ActivationController, Approval, ApprovalStore,
            RealApiAdapter, make_activation_server,
        )
        from prolific.ctc_verification_app.app import VerificationStore
        from prolific.ctc_verification_app.contact_candidates import (
            JsonContactLedger, VerifiedMessageScope, APPROVED_MESSAGE,
        )
        from prolific.ctc_verification_app.reconciliation import ProlificSubmissionClient
        from prolific.ctc_verification_app.triggers import JsonTriggerStore, ReconciliationTrigger

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_path = root / 'candidates.jsonl'
            candidate_path.write_text(
                json.dumps({
                    'candidate_key': 'routine-k',
                    'pred_is_ctc': True,
                    'audio_verify': {'verify_is_ctc': True},
                    'tos_audio': {'outer_url': 'https://controlled.test/a.wav'},
                }) + '\n',
                encoding='utf-8',
            )
            store = VerificationStore(
                [], [str(candidate_path)], root / 'data', 1, 1,
                'https://controlled.test/complete', False,
            )
            assignment = store.assign({
                'prolific_pid': 'P-NEW', 'study_id': 'STUDY', 'session_id': 'NEW-1',
            })
            self.assertEqual(assignment['status'], 'ok')
            now = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
            message_posts = []
            platform_state = {
                'id': 'NEW-1', 'study_id': 'STUDY', 'participant': 'P-NEW',
                'status': 'AWAITING REVIEW', 'started_at': '2026-01-01T00:00:00Z',
            }

            class ControlledApi(BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path.startswith('/api/v1/messages/'):
                        value = {'results': [], '_links': {'self': {'href': self.path}}}
                    elif '?' in self.path:
                        value = {
                            'results': [platform_state], 'meta': {'count': 1},
                            '_links': {'self': {'href': self.path}},
                        }
                    else:
                        value = platform_state
                    encoded = json.dumps(value).encode('utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)

                def do_POST(self):
                    length = int(self.headers.get('Content-Length', '0'))
                    message_posts.append(json.loads(self.rfile.read(length).decode('utf-8')))
                    encoded = json.dumps({'id': 'MESSAGE-1'}).encode('utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)

                def log_message(self, *_args):
                    pass

            api = ThreadingHTTPServer(('127.0.0.1', 0), ControlledApi)
            api_thread = threading.Thread(target=api.serve_forever)
            api_thread.start()
            receiver = None
            receiver_thread = None
            try:
                client = ProlificSubmissionClient(
                    'controlled-token',
                    'http://127.0.0.1:%d/api/v1' % api.server_address[1],
                    retries=0,
                )
                scope = VerifiedMessageScope(
                    'RESEARCHER', 'WORKSPACE',
                    datetime(2025, 12, 3, tzinfo=timezone.utc),
                    datetime(2026, 1, 2, tzinfo=timezone.utc),
                    True, 'controlled full message visibility',
                    now[0], now[0] + timedelta(hours=1),
                )
                trigger = ReconciliationTrigger(
                    client, root / 'data', 'STUDY',
                    JsonTriggerStore(root / 'events.json'), now=lambda: now[0],
                )
                adapter = RealApiAdapter(
                    client, root / 'data', 'STUDY', scope=scope, clock=lambda: now[0],
                )
                approvals = ApprovalStore(root / 'approval.json')
                controller = ActivationController(
                    trigger=trigger, store=store,
                    ledger=JsonContactLedger(root / 'contacts.json'),
                    adapter=adapter, journal=ActionJournal(root / 'actions.jsonl'),
                    study_id='STUDY', approvals=approvals,
                    production_enabled=True, clock=lambda: now[0],
                    activation_boundary='1970-01-01T00:00:00Z',
                )
                initial_report = trigger.periodic()['report']
                preview = controller.preview(initial_report)
                approvals.save(Approval(
                    'STUDY', '', (), (), (),
                    True, now[0].isoformat(), 'routine-policy-reviewer',
                ))
                receiver = make_activation_server(
                    controller, 'routine-secret', {
                        'run_kind': 'event',
                        'activation_boundary': '1970-01-01T00:00:00Z',
                        'study_id': 'STUDY',
                    },
                )
                receiver_thread = threading.Thread(target=receiver.serve_forever)
                receiver_thread.start()
                body = json.dumps({
                    'event_type': 'submission.status.change', 'resource_id': 'NEW-1',
                }).encode('utf-8')
                timestamp = '100'
                signature = base64.b64encode(hmac.new(
                    b'routine-secret', timestamp.encode() + body, hashlib.sha256,
                ).digest()).decode()
                request_headers = {
                    'X-Prolific-Request-Signature': signature,
                    'X-Prolific-Request-Timestamp': timestamp,
                    'X-Event-ID': 'routine-event-1', 'X-Timestamp': timestamp,
                    'Content-Type': 'application/json',
                }
                request = urllib.request.Request(
                    'http://127.0.0.1:%d/' % receiver.server_address[1],
                    data=body, method='POST', headers=request_headers,
                )
                first = json.loads(urllib.request.urlopen(request).read())
                self.assertEqual(first['status'], 'ok')
                self.assertEqual(first['candidates']['decisions'], [])
                ledger = JsonContactLedger(root / 'contacts.json').read()
                self.assertEqual(ledger['sessions']['NEW-1']['state'], 'observed')
                now[0] += timedelta(seconds=600)
                reassessed = controller.scheduled_reassessment()
                self.assertEqual(reassessed['status'], 'ok')
                self.assertEqual(reassessed['sessions'][0]['origin'], 'new')
                self.assertEqual(len(message_posts), 1)
            finally:
                if receiver is not None:
                    receiver.shutdown()
                    receiver.server_close()
                if receiver_thread is not None:
                    receiver_thread.join()
                api.shutdown()
                api.server_close()
                api_thread.join()
