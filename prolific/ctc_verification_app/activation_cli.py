"""Ticket 8 controlled activation entrypoint; production is opt-in."""
import argparse, json
from pathlib import Path
from .activation import ActionJournal

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--journal',type=Path,required=True); ap.add_argument('--disable',type=str); ap.add_argument('--show',action='store_true'); a=ap.parse_args(); j=ActionJournal(a.journal)
 if a.disable: j.disable(a.disable); print(json.dumps({'status':'disabled'})); return 0
 if a.show: print(json.dumps({'status':'ok','disabled':j.disabled,'journal':str(j.path)})); return 0
 ap.error('use --show or --disable; activation requires an explicitly wired operator command')
if __name__=='__main__': raise SystemExit(main())
