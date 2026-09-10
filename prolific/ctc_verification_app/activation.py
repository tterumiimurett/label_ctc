"""Concrete Ticket 8 activation composition and process-safe action journal."""
from __future__ import annotations
import fcntl, hashlib, json, os, threading, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ActionJournal:
    """Shared-file journal: process lock, fsync, intent-before-effect, kill switch."""
    def __init__(self, path: Path):
        self.path=path; self.lock_path=path.with_suffix(path.suffix+'.lock'); self.disable_path=path.with_suffix(path.suffix+'.disabled')
        self._thread=threading.RLock()
    def _lock(self):
        self.path.parent.mkdir(parents=True, exist_ok=True); h=self.lock_path.open('a+')
        fcntl.flock(h, fcntl.LOCK_EX); return h
    def _append(self, item):
        with self.path.open('a', encoding='utf-8') as h:
            h.write(json.dumps(item, ensure_ascii=False, sort_keys=True)+'\n'); h.flush(); os.fsync(h.fileno())
    @property
    def disabled(self):
        return self.disable_path.exists()
    def disable(self, reason):
        if not isinstance(reason,str) or not reason.strip(): raise ValueError('disable reason is required')
        with self._thread:
            h=self._lock()
            try:
                self.disable_path.parent.mkdir(parents=True, exist_ok=True)
                tmp=self.disable_path.with_name(self.disable_path.name+'.tmp')
                tmp.write_text(reason.strip()+'\n', encoding='utf-8'); os.replace(tmp,self.disable_path)
                with self.path.open('a', encoding='utf-8') as out:
                    out.write(json.dumps({'event_id':uuid.uuid4().hex,'kind':'disabled','reason':reason.strip(),'at':_now()},sort_keys=True)+'\n'); out.flush(); os.fsync(out.fileno())
            finally: fcntl.flock(h, fcntl.LOCK_UN); h.close()
    def begin(self, action, payload):
        with self._thread:
            h=self._lock()
            try:
                if self.disable_path.exists(): return None
                event={'event_id':uuid.uuid4().hex,'kind':'intent','action':action,'payload':payload,'at':_now()}
                self._append(event); return event['event_id']
            finally: fcntl.flock(h, fcntl.LOCK_UN); h.close()
    def finish(self, event_id, outcome, *, error=None):
        with self._thread:
            h=self._lock()
            try:
                self._append({'event_id':event_id,'kind':'outcome','outcome':outcome,'error':error,'at':_now()})
            finally: fcntl.flock(h, fcntl.LOCK_UN); h.close()
    def can_start(self): return not self.disable_path.exists()


class ActivationController:
    def __init__(self, *, trigger, store, ledger, adapter, journal: ActionJournal, study_id: str, production_enabled=False):
        self.trigger=trigger; self.store=store; self.ledger=ledger; self.adapter=adapter; self.journal=journal; self.study_id=study_id; self.production_enabled=production_enabled
    @staticmethod
    def derive_candidate_origin(context: Path|dict[str,Any]):
        value=json.loads(context.read_text()) if isinstance(context,Path) else context
        if isinstance(value,dict) and value.get('run_kind')=='event' and value.get('event_id'): return 'new'
        if isinstance(value,dict) and value.get('run_kind')=='backfill' and value.get('historical_snapshot') is True: return 'historical'
        return 'unknown'
    def preview(self, report):
        rows=[]
        for row in report.get('submissions',[]):
            if not isinstance(row,dict): continue
            action=row.get('proposed_action')
            if action=='release_claim_proposal': action='release_claim'
            rows.append({'session_id':row.get('session_id'),'study_id':row.get('study_id'),'participant_id':row.get('participant_id'),'action':action,'evidence':row.get('evidence',[])})
        result={'status':'preview','writes_performed':False,'actions':rows,'production_enabled':self.production_enabled,'disabled':self.journal.disabled}
        self.journal.begin('preview',{'sha256':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()})
        return result
    def reconcile_event(self, body, headers, secret):
        return self.trigger.handle(body,headers,secret)
    def current_reconcile(self): return self.trigger.periodic()
    def execute(self, *, provenance_context, approved_historical_sessions=None, activate=False):
        if self.production_enabled and not activate: raise PermissionError('explicit activation approval required')
        from .contact_candidates import build_contact_candidates
        from .outbound import send_approved_return_requests
        report=self.current_reconcile().get('report',{})
        if report.get('status')!='ok': return {'status':'pending','report':report}
        origin=self.derive_candidate_origin(provenance_context)
        results=[]
        for row in report.get('submissions',[]):
            if not isinstance(row,dict) or row.get('study_id')!=self.study_id: continue
            sid,pid=row.get('session_id'),row.get('participant_id')
            if not isinstance(sid,str) or not isinstance(pid,str): continue
            action=row.get('proposed_action')
            if action=='release_claim_proposal': action='release_claim'
            if action not in {'archived_result','release_claim','review_timeout_with_result'}: continue
            if not self.journal.can_start(): return {'status':'disabled','results':results}
            intent=self.journal.begin(action,{'session_id':sid,'study_id':self.study_id,'participant_id':pid})
            if not intent: return {'status':'disabled','results':results}
            obs={'id':sid,'study_id':self.study_id,'participant':{'id':pid},'status':row.get('status')}
            try:
                if row.get('status')=='RETURNED': outcome=self.store.reconcile_returned(obs)
                elif row.get('status')=='TIMED OUT': outcome=self.store.reconcile_timed_out(obs)
                else: outcome={'status':'manual_review','reason':'timeout result requires human review'}
                self.journal.finish(intent,'completed'); results.append({'session_id':sid,'action':action,'outcome':outcome})
            except Exception as e:
                self.journal.finish(intent,'failed',error=type(e).__name__); results.append({'session_id':sid,'action':action,'status':'failed'})
        fresh=self.adapter.reconcile()
        if fresh.get('status')!='ok': return {'status':'pending','origin':origin,'results':results,'report':fresh}
        candidates=build_contact_candidates(fresh,self.ledger,self.adapter,candidate_origin=origin)
        outbound=send_approved_return_requests(candidates,self.ledger,self.adapter,approved_sessions=approved_historical_sessions,historical_sessions=approved_historical_sessions,enabled=self.production_enabled and activate)
        return {'status':'ok','origin':origin,'results':results,'candidates':candidates,'outbound':outbound}
