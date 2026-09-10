"""Ticket 8 operator entrypoints; all mutation paths default off."""
import argparse, json
from pathlib import Path
from .activation import ActionJournal, ApprovalStore, Approval

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--journal',type=Path,required=True); sub=ap.add_subparsers(dest='command',required=True)
 d=sub.add_parser('disable'); d.add_argument('reason')
 s=sub.add_parser('status')
 v=sub.add_parser('preview'); v.add_argument('--report',type=Path,required=True)
 a=sub.add_parser('approve'); a.add_argument('--approval',type=Path,required=True); a.add_argument('--study-id',required=True); a.add_argument('--preview-sha256',required=True); a.add_argument('--approved-by',required=True); a.add_argument('--session',action='append',default=[]); a.add_argument('--historical-session',action='append',default=[])
 args=ap.parse_args(); journal=ActionJournal(args.journal)
 if args.command=='disable': journal.disable(args.reason); print(json.dumps({'status':'disabled'})); return 0
 if args.command=='status': print(json.dumps({'status':'ok','disabled':journal.disabled})); return 0
 if args.command=='preview':
  report=json.loads(args.report.read_text()); rows=report.get('submissions',[]); print(json.dumps({'status':'preview','writes_performed':False,'actions':rows},sort_keys=True)); return 0
 if args.command=='approve':
  ApprovalStore(args.approval).save(Approval(args.study_id,args.preview_sha256,tuple(sorted(args.session)),tuple(sorted(args.historical_session)),__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'{}'.format(args.approved_by))); print(json.dumps({'status':'approved','production':False})); return 0
 return 2
if __name__=='__main__': raise SystemExit(main())
