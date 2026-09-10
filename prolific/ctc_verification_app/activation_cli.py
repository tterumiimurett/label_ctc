"""Ticket 8 operator entrypoints; all mutation paths default off."""
import argparse, json
from pathlib import Path
from .activation import ActionJournal, ApprovalStore, Approval, ActivationController, RealApiAdapter, make_activation_server
from .reconciliation import ProlificSubmissionClient
from .triggers import JsonTriggerStore, ReconciliationTrigger
from .app import VerificationStore
from .contact_candidates import JsonContactLedger

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--journal',type=Path,required=True); sub=ap.add_subparsers(dest='command',required=True)
 d=sub.add_parser('disable'); d.add_argument('reason')
 s=sub.add_parser('status')
 v=sub.add_parser('preview'); v.add_argument('--report',type=Path,required=True)
 r=sub.add_parser('receiver'); r.add_argument('--config',type=Path,required=True); r.add_argument('--secret',required=True)
 y=sub.add_parser('scheduler'); y.add_argument('--config',type=Path,required=True); y.add_argument('--interval',type=float,default=300)
 a=sub.add_parser('approve'); a.add_argument('--approval',type=Path,required=True); a.add_argument('--study-id',required=True); a.add_argument('--preview-sha256',required=True); a.add_argument('--approved-by',required=True); a.add_argument('--session',action='append',default=[]); a.add_argument('--historical-session',action='append',default=[])
 args=ap.parse_args(); journal=ActionJournal(args.journal)
 if args.command in {'receiver','scheduler'}:
  config=json.loads(args.config.read_text(encoding='utf-8')); base=config['base_url']; study=config['study_id']; data=Path(config['data_dir']); token=config.get('token')
  if not token: raise SystemExit('missing configured API token; no live validation performed')
  client=ProlificSubmissionClient(token,base); trigger=ReconciliationTrigger(client,data,study,JsonTriggerStore(data/'events.json')); store=VerificationStore([],config['auto_labels'],data,int(config.get('bundle_size',1)),int(config.get('redundancy',1)),config.get('completion_url','https://app.prolific.com/submissions/complete'),False); adapter=RealApiAdapter(client,data,study); controller=ActivationController(trigger=trigger,store=store,ledger=JsonContactLedger(data/'contacts.json'),adapter=adapter,journal=journal,study_id=study,approvals=ApprovalStore(data/'approval.json'),production_enabled=False)
  if args.command=='receiver': server=make_activation_server(controller,args.secret,{'run_kind':'event','activation_boundary':config.get('activation_boundary')},host=config.get('host','127.0.0.1'),port=int(config.get('port',0))); print(json.dumps({'status':'listening','address':server.server_address})); server.serve_forever()
  import threading; stop=threading.Event(); from .triggers import run_periodic; run_periodic(trigger,args.interval,stop); return 0
 if args.command=='disable': journal.disable(args.reason); print(json.dumps({'status':'disabled'})); return 0
 if args.command=='status': print(json.dumps({'status':'ok','disabled':journal.disabled})); return 0
 if args.command=='preview':
  report=json.loads(args.report.read_text()); rows=report.get('submissions',[]); print(json.dumps({'status':'preview','writes_performed':False,'actions':rows},sort_keys=True)); return 0
 if args.command=='approve':
  ApprovalStore(args.approval).save(Approval(args.study_id,args.preview_sha256,tuple(sorted(set(args.session)|set(args.historical_session))),tuple(sorted(args.historical_session)),tuple(sorted(set(args.session)-set(args.historical_session))),__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'{}'.format(args.approved_by))); print(json.dumps({'status':'approved','production':False})); return 0
 return 2
if __name__=='__main__': raise SystemExit(main())
