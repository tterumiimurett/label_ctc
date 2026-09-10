import json, tempfile, unittest
from pathlib import Path
from unittest.mock import Mock
from prolific.ctc_verification_app.activation import ActionJournal, ActivationController

class Ticket08Test(unittest.TestCase):
 def setup(self, production=False):
  d=tempfile.TemporaryDirectory(); root=Path(d.name); journal=ActionJournal(root/'actions.jsonl')
  trigger=Mock(); trigger.periodic.return_value={'report':{'status':'ok','writes_performed':False,'submissions':[]}}
  adapter=Mock(); adapter.reconcile.return_value={'status':'ok','submissions':[]}
  return d,root,ActivationController(trigger=trigger,store=Mock(),ledger=Mock(),adapter=adapter,journal=journal,study_id='STUDY',production_enabled=production)
 def test_provenance_is_durable_and_unknown_is_manual(self):
  d,r,c=self.setup(); self.assertEqual(c.derive_candidate_origin({'run_kind':'event','event_id':'E','activation_boundary':'2026-01-01','study_id':'STUDY'}, accepted_event={'event_id':'E','study_id':'STUDY'}),'new'); self.assertEqual(c.derive_candidate_origin({'run_kind':'backfill','historical_snapshot':True}),'historical'); self.assertEqual(c.derive_candidate_origin({'run_kind':'manual'}),'unknown'); d.cleanup()
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
                from prolific.ctc_verification_app.activation import ActionJournal, ActivationController
                controller=ActivationController(trigger=trigger,store=store,ledger=JsonContactLedger(root/'contacts.json'),adapter=RealApiAdapter(client,root/'data','STUDY'),journal=ActionJournal(root/'actions.jsonl'),study_id='STUDY',approvals=ApprovalStore(root/'approval.json'))
                body=json.dumps({'event_type':'submission.status.change','resource_id':'S1'}).encode(); secret='secret'; ts='100'; sig=base64.b64encode(hmac.new(secret.encode(),ts.encode()+body,hashlib.sha256).digest()).decode()
                result=controller.handle_signed_event(body,{'X-Prolific-Request-Signature':sig,'X-Prolific-Request-Timestamp':ts,'X-Event-ID':'E1','X-Timestamp':'100'},secret,{'run_kind':'event','event_id':'E1','activation_boundary':'2026-01-01'})
                self.assertEqual(result['status'],'ok'); self.assertEqual(result['origin'],'new'); self.assertEqual(result['results'][0]['outcome']['action'],'released_claim')
            finally: server.shutdown(); server.server_close(); thread.join()
