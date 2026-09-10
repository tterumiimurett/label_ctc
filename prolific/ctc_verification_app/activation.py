"""Ticket 8 concrete activation pipeline."""
from __future__ import annotations
import fcntl, hashlib, json, os, threading, uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol

from .reconciliation import reconcile_current_state
from .contact_candidates import ProlificFreshReconciliation, VerifiedMessageScope


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

class ActionJournal:
    """Process-shared journal. Every effect has an fsynced intent first."""
    def __init__(self, path: Path):
        self.path=path; self.lock_path=path.with_suffix(path.suffix+'.lock'); self.disable_path=path.with_suffix(path.suffix+'.disabled'); self._thread=threading.RLock()
    def _locked(self) -> Any:
        self.path.parent.mkdir(parents=True, exist_ok=True); h=self.lock_path.open('a+'); fcntl.flock(h,fcntl.LOCK_EX); return h
    def _append(self, value: dict[str, Any]) -> None:
        with self.path.open('a',encoding='utf-8') as h: h.write(json.dumps(value,sort_keys=True,ensure_ascii=False)+'\n'); h.flush(); os.fsync(h.fileno())
    @property
    def disabled(self): return self.disable_path.exists()
    def disable(self, reason: str):
        if not reason.strip(): raise ValueError('disable reason is required')
        with self._thread:
            h=self._locked()
            try:
                tmp=self.disable_path.with_name(self.disable_path.name+'.tmp'); tmp.write_text(reason.strip()+'\n',encoding='utf-8'); fd=os.open(tmp, os.O_RDONLY); os.fsync(fd); os.close(fd); os.replace(tmp,self.disable_path); parent_fd=os.open(self.disable_path.parent, os.O_DIRECTORY); os.fsync(parent_fd); os.close(parent_fd); self._append({'kind':'disabled','reason':reason.strip(),'at':utc_now()})
            finally: fcntl.flock(h,fcntl.LOCK_UN); h.close()
    def begin(self, action: str, payload: dict[str, Any]) -> str | None:
        with self._thread:
            h=self._locked()
            try:
                if self.disable_path.exists(): return None
                eid=uuid.uuid4().hex; self._append({'kind':'intent','event_id':eid,'action':action,'payload':payload,'at':utc_now()}); return eid
            finally: fcntl.flock(h,fcntl.LOCK_UN); h.close()
    def finish(self, eid: str, outcome: str, error: str | None = None) -> None:
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
    routine_sessions: tuple[str,...] = ()
    routine_enabled: bool = False
    approved_at: str = ''
    approved_by: str = ''

class ApprovalStore:
    def __init__(self, path: Path): self.path=path; self.lock_path=path.with_suffix(path.suffix+'.lock'); self._thread=threading.RLock()
    def _lock(self):
        self.path.parent.mkdir(parents=True,exist_ok=True); h=self.lock_path.open('a+'); fcntl.flock(h,fcntl.LOCK_EX); return h
    def save(self, approval: Approval):
        with self._thread:
            h=self._lock()
            try:
                tmp=self.path.with_name(self.path.name+'.'+uuid.uuid4().hex+'.tmp'); tmp.write_text(json.dumps(approval.__dict__,sort_keys=True)+'\n',encoding='utf-8'); fd=os.open(tmp, os.O_RDONLY); os.fsync(fd); os.close(fd); os.replace(tmp,self.path); parent_fd=os.open(self.path.parent, os.O_DIRECTORY); os.fsync(parent_fd); os.close(parent_fd)
            finally: fcntl.flock(h,fcntl.LOCK_UN); h.close()
    def load(self):
        with self._thread:
            h=self._lock()
            try:
                if not self.path.exists(): return None
                value=json.loads(self.path.read_text(encoding='utf-8')); return Approval(value['study_id'],value['preview_sha256'],tuple(value['sessions']),tuple(value['historical_sessions']),tuple(value.get('routine_sessions',())),value.get('routine_enabled',False),value.get('approved_at',''),value.get('approved_by',''))
            finally: fcntl.flock(h,fcntl.LOCK_UN); h.close()

class RealApiAdapter:
    """Adapter used by activation; reads current API state through the reviewed reader."""
    def __init__(self, reader, data_dir: Path, study_id: str, scope: VerifiedMessageScope | None = None, clock: Any = None):
        self.reader=reader; self.data_dir=data_dir; self.study_id=study_id; self.fresh=ProlificFreshReconciliation(reader,data_dir,study_id,scope=scope,now=clock() if clock else None); self.clock=clock
    def reconcile(self):
        if self.clock: self.fresh.now=self.clock()
        return self.fresh.reconcile()
    def inspect_messages(self, **kwargs): return self.fresh.inspect_messages(**kwargs)
    def send_message(self, **kwargs): return self.fresh.send_message(**kwargs)

class GuardedOutboundAdapter:
    """Adds per-recipient intent/kill checks around the reviewed outbound adapter."""
    def __init__(self, adapter: Any, journal: ActionJournal):
        self.adapter = adapter
        self.journal = journal
    def reconcile(self) -> dict[str, Any]:
        return self.adapter.reconcile()
    def inspect_messages(self, **kwargs: Any) -> str:
        return self.adapter.inspect_messages(**kwargs)
    def send_message(self, *, recipient_id: str, body: str, study_id: str) -> dict[str, Any]:
        event_id = self.journal.begin("recipient_message", {"recipient_id": recipient_id, "study_id": study_id})
        if event_id is None:
            raise PermissionError("future actions disabled")
        try:
            response = self.adapter.send_message(recipient_id=recipient_id, body=body, study_id=study_id)
        except Exception as error:
            self.journal.finish(event_id, "delivery_unknown", type(error).__name__)
            raise
        self.journal.finish(event_id, "accepted")
        return response

class ActivationController:
    def __init__(self, *, trigger, store, ledger, adapter, journal: ActionJournal, study_id: str, approvals: ApprovalStore | None = None, production_enabled: bool = False, clock: Any = None, activation_boundary: str | None = None):
        self.trigger=trigger; self.store=store; self.ledger=ledger; self.adapter=adapter; self.journal=journal; self.study_id=study_id; self.approvals=approvals; self.production_enabled=production_enabled; self.clock=clock; self.activation_boundary=activation_boundary
    def _parse_boundary(self, value: Any) -> datetime | None:
        if not value: return None
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    def derive_candidate_origin(self, context: Path | dict[str, Any], *, accepted_event: dict[str, Any] | None = None) -> str:
        value=json.loads(context.read_text(encoding='utf-8')) if isinstance(context,Path) else context
        if not isinstance(value,dict): return 'unknown'
        if value.get('run_kind')=='event' and accepted_event and value.get('event_id')==accepted_event.get('event_id') and value.get('study_id')==accepted_event.get('study_id') and (self._parse_boundary(value.get('activation_boundary')) == self._parse_boundary(self.activation_boundary)) and accepted_event.get('event_timestamp', 0) >= accepted_event.get('activation_timestamp', 0):
            return 'new'
        if value.get('run_kind')=='backfill' and value.get('historical_snapshot') is True: return 'historical'
        return 'unknown'
    def _rows(self, report: dict[str, Any]) -> list[dict[str, Any]]:
        rows=[]
        for row in report.get('submissions',[]):
            if not isinstance(row,dict): continue
            action=row.get('proposed_action')
            mapping={'release_claim_proposal':'release_claim','review_returned_with_result':'archive_returned_result','review_timeout_with_result':'archive_timed_out_result','review_missing_result':'contact_candidate'}
            rows.append({'session_id':row.get('session_id'),'study_id':row.get('study_id'),'participant_id':row.get('participant_id'),'action':mapping.get(action,action),'evidence':row.get('evidence',[]),'status':row.get('status')})
        return rows
    def preview(self, report: dict[str, Any]) -> dict[str, Any]:
        rows=self._rows(report); digest=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(); result={'status':'preview','study_id':self.study_id,'preview_sha256':digest,'actions':rows,'historical_sessions':[r['session_id'] for r in rows if r['action']=='contact_candidate'],'writes_performed':False}
        eid=self.journal.begin('preview',{'study_id':self.study_id,'preview_sha256':digest});
        if eid: self.journal.finish(eid,'recorded')
        return result
    def approve(self, preview, approved_by:str, sessions:set[str], historical_sessions:set[str]):
        if preview.get('study_id')!=self.study_id or not approved_by.strip(): raise ValueError('approval identity/study mismatch')
        allowed={r['session_id'] for r in preview['actions']};
        if not sessions <= allowed or not historical_sessions <= allowed: raise ValueError('approval contains unlisted session')
        approval=Approval(self.study_id,preview['preview_sha256'],tuple(sorted(sessions)),tuple(sorted(historical_sessions)),tuple(sorted(sessions-set(historical_sessions))),False,utc_now(),approved_by); self.approvals.save(approval); return approval
    def current_reconcile(self): return self.trigger.periodic()
    def handle_signed_event(self, body, headers, secret, context):
        result=self.trigger.handle(body,headers,secret)
        if result.status not in {'reconciled'}: return result
        payload=json.loads(body); report=result.report or {}; context_value=json.loads(context.read_text(encoding='utf-8')) if isinstance(context,Path) else context
        event_id=headers.get('X-Event-ID') or headers.get('x-event-id')
        normalized_headers = {key.lower(): value for key, value in headers.items()}
        event_id = normalized_headers.get('x-event-id', '')
        payload = json.loads(body)
        resource_id = payload.get('resource_id')
        event_record = self.trigger.store.accepted_event(event_id, resource_id) if hasattr(self.trigger.store, 'accepted_event') else None
        payload_event = event_record.get('payload', {})
        accepted = {'event_id': event_id, 'resource_id': payload_event.get('resource_id'), 'study_id': self.study_id, 'event_timestamp': event_record.get('timestamp', 0), 'activation_timestamp': self._activation_epoch()}
        if event_record.get('stage') != 'completed' or not accepted['resource_id']:
            return {'status': 'pending', 'reason': 'accepted_event_not_durable'}
        context_value = json.loads(context.read_text(encoding='utf-8')) if isinstance(context, Path) else dict(context)
        context_value['event_id'] = accepted['event_id']
        context_value['study_id'] = report.get('study_id')
        context_value['activation_boundary'] = self.activation_boundary
        return self.execute(provenance_context=context_value, report=report, accepted_event=accepted)
    def _activation_epoch(self) -> int:
        if not self.activation_boundary: return 0
        return int(datetime.fromisoformat(self.activation_boundary.replace('Z', '+00:00')).timestamp())
    def execute(self, *, provenance_context, report=None, accepted_event=None, session_id: str | None = None):
        if self.production_enabled and self.approvals is None: raise PermissionError('persisted approval store is required')
        if report is None: report=self.current_reconcile().get('report',{})
        if report.get('status')!='ok': return {'status':'pending','report':report}
        if session_id is not None:
            report = {**report, 'submissions': [row for row in report.get('submissions', []) if row.get('session_id') == session_id]}
        preview=self.preview(report); approval=self.approvals.load() if self.approvals else None
        if self.production_enabled:
            if not approval or approval.study_id != self.study_id or not approval.routine_enabled: return {'status':'blocked','reason':'routine_policy_approval_missing'}
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
            current_status=str(current.get('status','')).upper().replace('_','-').replace(' ', '-')
            if row['action']=='archive_returned_result' and current_status != 'RETURNED': continue
            if row['action']=='archive_timed_out_result' and current_status != 'TIMED-OUT': continue
            if row['action']=='release_claim' and current_status not in {'RETURNED','TIMED-OUT'}: continue
            action=row['action']; eid=self.journal.begin(action,{'session_id':sid,'study_id':self.study_id,'participant_id':row['participant_id']})
            if not eid: break
            try:
                if action=='archive_returned_result': outcome=self.store.reconcile_returned({'id':sid,'study_id':self.study_id,'participant':{'id':row['participant_id']},'status':'RETURNED'})
                elif action=='archive_timed_out_result': outcome=self.store.reconcile_timed_out({'id':sid,'study_id':self.study_id,'participant':{'id':row['participant_id']},'status':'TIMED-OUT'})
                elif action=='release_claim':
                    if current_status == 'RETURNED': outcome=self.store.reconcile_returned({'id':sid,'study_id':self.study_id,'participant':{'id':row['participant_id']},'status':'RETURNED'})
                    else: outcome=self.store.reconcile_timed_out({'id':sid,'study_id':self.study_id,'participant':{'id':row['participant_id']},'status':'TIMED-OUT'})
                else: outcome={'status':'manual_review','reason':'contact handled after candidate phase'}
                result={'session_id':sid,'action':action,'outcome':outcome}; self.journal.finish(eid, 'manual_review' if outcome.get('status') == 'manual_review' else ('completed' if outcome.get('status') in {'processed','already_processed'} else 'failed'), outcome.get('reason')); results.append(result)
            except Exception as error: self.journal.finish(eid,'failed',type(error).__name__); results.append({'session_id':sid,'action':action,'status':'failed'})
        from .contact_candidates import build_contact_candidates
        from .outbound import send_approved_return_requests
        fresh=self.adapter.reconcile()
        if fresh.get('status')!='ok': return {'status':'pending','origin':origin,'results':results,'report':fresh}
        if session_id is not None:
            fresh = {**fresh, 'submissions': [row for row in fresh.get('submissions', []) if row.get('session_id') == session_id]}
        candidate_report=build_contact_candidates(fresh,self.ledger,self.adapter,candidate_origin=origin,now=self.clock() if self.clock else None)
        historical=set(approval.historical_sessions) if approval else set()
        outbound=send_approved_return_requests(candidate_report,self.ledger,GuardedOutboundAdapter(self.adapter,self.journal),approved_sessions={item['session_id'] for item in candidate_report.get('decisions', []) if item.get('decision') == 'candidate'} if approval and approval.routine_enabled and origin == 'new' else set(approval.routine_sessions) if approval else set(),historical_sessions=historical,enabled=self.production_enabled)
        return {'status':'ok','origin':origin,'results':results,'preview':preview,'candidates':candidate_report,'outbound':outbound}

    def scheduled_reassessment(self) -> dict[str, Any]:
        """Reassess durable accepted events without requiring a new webhook."""
        periodic = self.current_reconcile()
        report = periodic.get('report', {})
        if report.get('status') != 'ok':
            return {'status': 'pending', 'report': report, 'sessions': []}
        state = self.trigger.store._read() if hasattr(self.trigger.store, '_read') else {}
        sessions: list[dict[str, Any]] = []
        for event_id, event in state.get('events', {}).items():
            if event.get('stage') != 'completed':
                continue
            payload = event.get('payload', {})
            resource_id = payload.get('resource_id')
            row = next((item for item in report.get('submissions', []) if item.get('session_id') == resource_id), None)
            if not isinstance(row, dict):
                continue
            accepted = {
                'event_id': event_id, 'resource_id': resource_id,
                'study_id': row.get('study_id'),
                'event_timestamp': event.get('timestamp', 0),
                'activation_timestamp': self._activation_epoch(),
            }
            context = {
                'run_kind': 'event', 'event_id': event_id,
                'study_id': row.get('study_id'),
                'activation_boundary': self.activation_boundary,
            }
            sessions.append(self.execute(
                provenance_context=context, report=report,
                accepted_event=accepted, session_id=resource_id,
            ))
        return {'status': 'ok', 'report': report, 'sessions': sessions}


def make_activation_server(controller: ActivationController, secret: str, context: dict[str, Any], host: str='127.0.0.1', port: int=0):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length=int(self.headers.get('Content-Length','0')); body=self.rfile.read(length)
            result=controller.handle_signed_event(body,dict(self.headers.items()),secret,context)
            raw=json.dumps(result if isinstance(result,dict) else {'status':result.status}).encode(); self.send_response(200 if isinstance(result,dict) or result.accepted else 401); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        def log_message(self,*args): pass
    return ThreadingHTTPServer((host,port),Handler)
