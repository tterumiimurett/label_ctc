"""Ticket 8 concrete activation pipeline."""
from __future__ import annotations
import fcntl, hashlib, json, os, threading, uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from .reconciliation import reconcile_current_state


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

class ActionJournal:
    """Process-shared journal. Every effect has an fsynced intent first."""
    def __init__(self, path: Path):
        self.path=path; self.lock_path=path.with_suffix(path.suffix+'.lock'); self.disable_path=path.with_suffix(path.suffix+'.disabled'); self._thread=threading.RLock()
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True); h=self.lock_path.open('a+'); fcntl.flock(h,fcntl.LOCK_EX); return h
    def _append(self, value):
        with self.path.open('a',encoding='utf-8') as h: h.write(json.dumps(value,sort_keys=True,ensure_ascii=False)+'\n'); h.flush(); os.fsync(h.fileno())
    @property
    def disabled(self): return self.disable_path.exists()
    def disable(self, reason: str):
        if not reason.strip(): raise ValueError('disable reason is required')
        with self._thread:
            h=self._locked()
            try:
                tmp=self.disable_path.with_name(self.disable_path.name+'.tmp'); tmp.write_text(reason.strip()+'\n',encoding='utf-8'); os.replace(tmp,self.disable_path); self._append({'kind':'disabled','reason':reason.strip(),'at':utc_now()})
            finally: fcntl.flock(h,fcntl.LOCK_UN); h.close()
    def begin(self, action: str, payload: dict[str,Any]) -> str|None:
        with self._thread:
            h=self._locked()
            try:
                if self.disable_path.exists(): return None
                eid=uuid.uuid4().hex; self._append({'kind':'intent','event_id':eid,'action':action,'payload':payload,'at':utc_now()}); return eid
            finally: fcntl.flock(h,fcntl.LOCK_UN); h.close()
    def finish(self, eid: str, outcome: str, error: str|None=None):
        with self._thread:
            h=self._locked()
            try: self._append({'kind':'outcome','event_id':eid,'outcome':outcome,'error':error,'at':utc_now()})
            finally: fcntl.flock(h,fcntl.LOCK_UN); h.close()

@dataclass(frozen=True)
class Approval:
    study_id: str
    preview_sha256: str
    sessions: tuple[str,...]
    historical_sessions: tuple[str,...]
    approved_at: str
    approved_by: str

class ApprovalStore:
    def __init__(self,path:Path): self.path=path; self.lock=path.with_suffix(path.suffix+'.lock')
    def save(self, approval: Approval):
        self.path.parent.mkdir(parents=True,exist_ok=True); tmp=self.path.with_name(self.path.name+'.tmp'); tmp.write_text(json.dumps(approval.__dict__,sort_keys=True)+'\n'); os.replace(tmp,self.path)
    def load(self):
        if not self.path.exists(): return None
        value=json.loads(self.path.read_text()); return Approval(value['study_id'],value['preview_sha256'],tuple(value['sessions']),tuple(value['historical_sessions']),value['approved_at'],value['approved_by'])

class RealApiAdapter:
    """Adapter used by activation; reads current API state through the reviewed reader."""
    def __init__(self, reader, data_dir: Path, study_id: str): self.reader=reader; self.data_dir=data_dir; self.study_id=study_id
    def reconcile(self): return reconcile_current_state(self.reader,self.data_dir,self.study_id)
    def inspect_messages(self, **kwargs): return "unavailable"
    def send_message(self, **kwargs): return self.reader.send_message(**kwargs)

class ActivationController:
    def __init__(self, *, trigger, store, ledger, adapter, journal:ActionJournal, study_id:str, approvals:ApprovalStore|None=None, production_enabled=False):
        self.trigger=trigger; self.store=store; self.ledger=ledger; self.adapter=adapter; self.journal=journal; self.study_id=study_id; self.approvals=approvals; self.production_enabled=production_enabled
    @staticmethod
    def derive_candidate_origin(context:Path|dict[str,Any], *, accepted_event:dict[str,Any]|None=None):
        value=json.loads(context.read_text()) if isinstance(context,Path) else context
        if not isinstance(value,dict): return 'unknown'
        if value.get('run_kind')=='event' and accepted_event and value.get('event_id')==accepted_event.get('event_id') and value.get('study_id')==accepted_event.get('study_id') and value.get('activation_boundary'):
            return 'new'
        if value.get('run_kind')=='backfill' and value.get('historical_snapshot') is True: return 'historical'
        return 'unknown'
    def _rows(self,report):
        rows=[]
        for row in report.get('submissions',[]):
            if not isinstance(row,dict): continue
            action=row.get('proposed_action')
            mapping={'release_claim_proposal':'release_claim','review_returned_with_result':'archive_returned_result','review_timeout_with_result':'archive_timed_out_result','review_missing_result':'contact_candidate'}
            rows.append({'session_id':row.get('session_id'),'study_id':row.get('study_id'),'participant_id':row.get('participant_id'),'action':mapping.get(action,action),'evidence':row.get('evidence',[]),'status':row.get('status')})
        return rows
    def preview(self, report):
        rows=self._rows(report); digest=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(); result={'status':'preview','study_id':self.study_id,'preview_sha256':digest,'actions':rows,'historical_sessions':[r['session_id'] for r in rows if r['action']=='contact_candidate'],'writes_performed':False}
        eid=self.journal.begin('preview',{'study_id':self.study_id,'preview_sha256':digest});
        if eid: self.journal.finish(eid,'recorded')
        return result
    def approve(self, preview, approved_by:str, sessions:set[str], historical_sessions:set[str]):
        if preview.get('study_id')!=self.study_id or not approved_by.strip(): raise ValueError('approval identity/study mismatch')
        allowed={r['session_id'] for r in preview['actions']};
        if not sessions <= allowed or not historical_sessions <= allowed: raise ValueError('approval contains unlisted session')
        approval=Approval(self.study_id,preview['preview_sha256'],tuple(sorted(sessions)),tuple(sorted(historical_sessions)),utc_now(),approved_by); self.approvals.save(approval); return approval
    def current_reconcile(self): return self.trigger.periodic()
    def handle_signed_event(self, body, headers, secret, context):
        result=self.trigger.handle(body,headers,secret)
        if result.status not in {'reconciled'}: return result
        payload=json.loads(body); report=result.report or {}; context_value=json.loads(context.read_text()) if isinstance(context,Path) else context
        context_value={**context_value,'event_id':headers.get('X-Event-ID') or headers.get('x-event-id'),'study_id':self.study_id}
        return self.execute(provenance_context=context_value, report=report, accepted_event=context_value)
    def execute(self, *, provenance_context, report=None, accepted_event=None):
        if self.production_enabled and self.approvals is None: raise PermissionError('persisted approval store is required')
        if report is None: report=self.current_reconcile().get('report',{})
        if report.get('status')!='ok': return {'status':'pending','report':report}
        preview=self.preview(report); approval=self.approvals.load() if self.approvals else None
        if self.production_enabled:
            if not approval or approval.study_id!=self.study_id or approval.preview_sha256!=preview['preview_sha256']: return {'status':'blocked','reason':'approval_missing_or_stale'}
        origin=self.derive_candidate_origin(provenance_context,accepted_event=accepted_event)
        selected=set(approval.sessions) if approval else {r['session_id'] for r in preview['actions'] if r['action']!='contact_candidate'}
        results=[]
        for row in preview['actions']:
            sid=row['session_id'];
            if sid not in selected or row['study_id']!=self.study_id or not isinstance(row['participant_id'],str): continue
            if self.journal.disabled: break
            fresh=self.adapter.reconcile()
            current=next((x for x in fresh.get('submissions',[]) if x.get('session_id')==sid),None)
            if fresh.get('status')!='ok' or not current or current.get('participant_id')!=row['participant_id']: continue
            action=row['action']; eid=self.journal.begin(action,{'session_id':sid,'study_id':self.study_id,'participant_id':row['participant_id']})
            if not eid: break
            try:
                if action=='archive_returned_result': outcome=self.store.reconcile_returned({'id':sid,'study_id':self.study_id,'participant':{'id':row['participant_id']},'status':'RETURNED'})
                elif action=='archive_timed_out_result': outcome=self.store.reconcile_timed_out({'id':sid,'study_id':self.study_id,'participant':{'id':row['participant_id']},'status':'TIMED-OUT'})
                elif action=='release_claim': outcome=self.store.reconcile_timed_out({'id':sid,'study_id':self.study_id,'participant':{'id':row['participant_id']},'status':'TIMED-OUT'})
                else: outcome={'status':'manual_review','reason':'contact handled after candidate phase'}
                result={'session_id':sid,'action':action,'outcome':outcome}; self.journal.finish(eid,'completed' if outcome.get('status') in {'processed','already_processed','manual_review'} else 'failed'); results.append(result)
            except Exception as error: self.journal.finish(eid,'failed',type(error).__name__); results.append({'session_id':sid,'action':action,'status':'failed'})
        return {'status':'ok','origin':origin,'results':results,'preview':preview}


def make_activation_server(controller: ActivationController, secret: str, context: dict[str, Any], host: str='127.0.0.1', port: int=0):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length=int(self.headers.get('Content-Length','0')); body=self.rfile.read(length)
            result=controller.handle_signed_event(body,dict(self.headers.items()),secret,context)
            raw=json.dumps(result if isinstance(result,dict) else {'status':result.status}).encode(); self.send_response(200 if isinstance(result,dict) or result.accepted else 401); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        def log_message(self,*args): pass
    return ThreadingHTTPServer((host,port),Handler)
