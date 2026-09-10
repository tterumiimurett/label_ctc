"""Pinned fd8bac6 real HTTP positive-path acceptance attempt; localhost/temp only."""
import base64,hashlib,hmac,json,sys,tempfile,threading
from datetime import datetime,timedelta,timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.request import Request,urlopen
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prolific.ctc_verification_app.activation import ActivationController,ActionJournal,Approval,ApprovalStore,RealApiAdapter,make_activation_server
from prolific.ctc_verification_app.app import VerificationStore
from prolific.ctc_verification_app.contact_candidates import JsonContactLedger,VerifiedMessageScope
from prolific.ctc_verification_app.reconciliation import ProlificSubmissionClient
from prolific.ctc_verification_app.triggers import JsonTriggerStore,ReconciliationTrigger
now=[datetime(2026,9,10,12,0,tzinfo=timezone.utc)]
clock=lambda:now[0]
boundary='2026-09-10T11:00:00Z'
state={'id':'S1','study_id':'STUDY','participant':'P1','status':'AWAITING REVIEW','started_at':'2026-09-10T11:50:00Z','entered_code':'NOCODE'}
old_state={**state,'id':'OLD','participant':'P-OLD','started_at':'2026-09-10T10:00:00Z'}
posts=[];gets=[]
class API(BaseHTTPRequestHandler):
 def output(self,data):
  raw=json.dumps(data).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def do_GET(self):
  gets.append(self.path)
  if self.path.startswith('/api/v1/messages/'):
   self.output({'results':[],'_links':{'self':{'href':self.path}}})
  elif self.path.startswith('/api/v1/submissions/?'):
   self.output({'results':[state,old_state],'meta':{'count':2},'_links':{'self':{'href':self.path}}})
  elif self.path.startswith('/api/v1/submissions/OLD'):
   self.output(old_state)
  elif self.path.startswith('/api/v1/submissions/S1'):
   self.output(state)
  else:self.send_error(404)
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));posts.append({'path':self.path,'body':body});self.output({'id':'M1'})
 def log_message(self,*a):pass
api=ThreadingHTTPServer(('127.0.0.1',0),API);ta=threading.Thread(target=api.serve_forever);ta.start()
receiver=None;tr=None
try:
 with tempfile.TemporaryDirectory() as d:
  root=Path(d);candidate=root/'candidates.jsonl';candidate.write_text(json.dumps({'candidate_key':'K','pred_is_ctc':True,'audio_verify':{'verify_is_ctc':True},'tos_audio':{'outer_url':'http://127.0.0.1/unused.wav'}})+'\n')
  store=VerificationStore([],[str(candidate)],root/'data',1,1,'https://example.test/complete',False)
  assert store.assign({'prolific_pid':'P1','study_id':'STUDY','session_id':'S1'})['status']=='ok'
  client=ProlificSubmissionClient('synthetic-only',f'http://127.0.0.1:{api.server_port}/api/v1',retries=0)
  trigger=ReconciliationTrigger(client,root/'data','STUDY',JsonTriggerStore(root/'events.json'),now=clock)
  scope=VerifiedMessageScope('R','W',now[0]-timedelta(days=1),now[0]+timedelta(days=1),True,'controlled API all message pages visible',now[0]-timedelta(minutes=1),now[0]+timedelta(days=1))
  adapter=RealApiAdapter(client,root/'data','STUDY',scope=scope,clock=clock)
  approvals=ApprovalStore(root/'approval.json');approvals.save(Approval(study_id='STUDY',preview_sha256='',sessions=(),historical_sessions=(),routine_enabled=True,approved_at=now[0].isoformat(),approved_by='synthetic-reviewer'))
  ledger=JsonContactLedger(root/'contacts.json')
  c=ActivationController(trigger=trigger,store=store,ledger=ledger,adapter=adapter,journal=ActionJournal(root/'journal.jsonl'),study_id='STUDY',approvals=approvals,production_enabled=True,clock=clock,activation_boundary=boundary)
  receiver=make_activation_server(c,'synthetic-secret',{'run_kind':'event','activation_boundary':boundary});tr=threading.Thread(target=receiver.serve_forever);tr.start()
  def event(eid):
   raw=json.dumps({'event_type':'submission.status.change','resource_id':'S1'}).encode();ts=str(int(now[0].timestamp()));sig=base64.b64encode(hmac.new(b'synthetic-secret',ts.encode()+raw,hashlib.sha256).digest()).decode()
   request=Request(f'http://127.0.0.1:{receiver.server_port}/',data=raw,headers={'Content-Type':'application/json','X-Prolific-Request-Signature':sig,'X-Prolific-Request-Timestamp':ts,'X-Event-ID':eid,'X-Timestamp':ts})
   with urlopen(request) as response:return json.loads(response.read())
  first=event('E1');now[0]+=timedelta(minutes=10);second=event('E2')
  print(json.dumps({'first':first,'after_ten_minutes':second,'ledger':ledger.read(),'message_GETs':[p for p in gets if '/messages/' in p],'POSTs':posts},indent=2))
  assert len(posts)==1 and posts[0]['body']['recipient_id']=='P1' and all(item['body']['recipient_id']!='P-OLD' for item in posts), 'cross-resource isolation failed'
finally:
 if receiver:receiver.shutdown();receiver.server_close();tr.join()
 api.shutdown();api.server_close();ta.join()
