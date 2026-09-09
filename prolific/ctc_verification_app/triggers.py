"""Read-only Prolific webhook receiver and scheduled reconciliation drain."""
from __future__ import annotations
import base64, fcntl, hashlib, hmac, json, os, tempfile, threading, time, uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Protocol
from .reconciliation import SubmissionReader, reconcile_current_state

class TriggerStore(Protocol):
    def begin(self, event_id: str, timestamp: int, payload: dict[str, Any]) -> tuple[str, str | None]: ...
    def finish(self, event_id: str, owner: str, stage: str, *, report: dict[str, Any] | None = None, error: str | None = None) -> bool: ...
    def retryable(self) -> list[tuple[str, dict[str, Any]]]: ...

class JsonTriggerStore:
    """Atomic process-safe ledger; reports are audit evidence linked to events."""
    def __init__(self, path: Path, *, processing_lease_seconds: float = 300.0):
        self.path, self.lease = path, processing_lease_seconds
        self.lock_path, self._thread_lock = path.with_suffix(path.suffix + ".lock"), threading.RLock()
    def _read(self):
        if not self.path.exists(): return {"events": {}, "latest_by_resource": {}}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("events", {}), dict): raise ValueError("invalid trigger ledger")
        value.setdefault("latest_by_resource", {}); return value
    def _write(self, state):
        self.path.parent.mkdir(parents=True, exist_ok=True); fd, tmp = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, sort_keys=True, indent=2); handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
    def _lock(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True); lock = self.lock_path.open("a+"); fcntl.flock(lock.fileno(), fcntl.LOCK_EX); return lock
    def begin(self, event_id, timestamp, payload):
        with self._thread_lock:
            lock = self._lock()
            try:
                state = self._read(); events = state["events"]; event = events.get(event_id); now = time.time()
                if event and event.get("stage") in {"completed", "ignored_wrong_study", "stale"}: return event["stage"], None
                expired = False
                if event and event.get("stage") == "processing":
                    if now - float(event.get("processing_started", 0)) < self.lease: return "busy", None
                    event["stage"] = "pending"; expired = True
                resource, latest = payload.get("resource_id"), state["latest_by_resource"].get(payload.get("resource_id"))
                if expired or (event and event.get("stage") == "pending"):
                    owner = uuid.uuid4().hex; events[event_id] = {**event, "stage": "processing", "processing_started": now, "owner": owner}; self._write(state); return "retry", owner
                if not event and latest and timestamp < latest["timestamp"]:
                    events[event_id] = {"timestamp": timestamp, "payload": payload, "stage": "stale"}; self._write(state); return "stale", None
                owner = uuid.uuid4().hex
                events[event_id] = {"timestamp": timestamp, "payload": payload, "stage": "processing", "processing_started": now, "owner": owner}
                if resource: state["latest_by_resource"][resource] = {"timestamp": timestamp, "event_id": event_id}
                self._write(state); return "new", owner
            finally: fcntl.flock(lock.fileno(), fcntl.LOCK_UN); lock.close()
    def finish(self, event_id, owner, stage, *, report=None, error=None):
        with self._thread_lock:
            lock = self._lock()
            try:
                state = self._read(); event = state["events"].get(event_id)
                if not event or event.get("owner") != owner: return False
                event["stage"] = stage; event["finished_at"] = time.time()
                if report is not None: event["report"] = report
                if error is not None: event["error"] = error
                self._write(state); return True
            finally: fcntl.flock(lock.fileno(), fcntl.LOCK_UN); lock.close()
    def retryable(self):
        with self._thread_lock:
            lock = self._lock()
            try:
                state = self._read(); now = time.time(); result=[]
                for event_id, event in state["events"].items():
                    if event.get("stage") == "pending" or (event.get("stage") == "processing" and now-float(event.get("processing_started",0)) >= self.lease): result.append((event_id, {**event["payload"], "_ledger_timestamp": event.get("timestamp", 0)}))
                return result
            finally: fcntl.flock(lock.fileno(), fcntl.LOCK_UN); lock.close()

def verify_signature(body: bytes, secret: str, signature: str, timestamp: str) -> bool:
    digest = hmac.new(secret.encode(), timestamp.encode() + body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)
@dataclass(frozen=True)
class TriggerResult: accepted: bool; status: str; report: dict[str, Any] | None = None
class ReconciliationTrigger:
    def __init__(self, reader, data_dir, study_id, store, *, valid_completion_codes=None, now=None, production_enabled=False):
        if production_enabled: raise ValueError("production execution is disabled")
        self.reader,self.data_dir,self.study_id,self.store=reader,data_dir,study_id,store; self.valid_completion_codes=valid_completion_codes; self.now=now or (lambda: datetime.now(timezone.utc))
    def _run(self): return reconcile_current_state(self.reader,self.data_dir,self.study_id,self.valid_completion_codes,now=self.now())
    def _process(self,event_id,payload,owner):
        try:
            detail=self.reader.get_submission(payload["resource_id"])
            if not isinstance(detail,dict) or detail.get("study_id") != self.study_id:
                self.store.finish(event_id,owner,"ignored_wrong_study",error="submission study does not match configured study"); return TriggerResult(True,"ignored_wrong_study")
            report=self._run()
            if report.get("status") != "ok":
                self.store.finish(event_id,owner,"pending",report=report,error=report.get("error","reconciliation failed")); return TriggerResult(True,"pending_retry",report)
            self.store.finish(event_id,owner,"completed",report=report); return TriggerResult(True,"reconciled",report)
        except Exception as error:
            self.store.finish(event_id,owner,"pending",error=str(error)); return TriggerResult(True,"pending_retry")
    def handle(self, body, headers, secret):
        normalized={key.lower():value for key,value in headers.items()}; signature=normalized.get("x-prolific-request-signature",""); timestamp_text=normalized.get("x-prolific-request-timestamp",""); event_id=normalized.get("x-event-id","")
        if not signature or not timestamp_text or not event_id or not verify_signature(body,secret,signature,timestamp_text): return TriggerResult(False,"rejected_signature")
        try:
            timestamp=int(timestamp_text); payload=json.loads(body.decode())
            if not isinstance(payload,dict) or payload.get("event_type") != "submission.status.change": return TriggerResult(False,"ignored_event")
            resource=payload.get("resource_id")
            if not isinstance(resource,str) or not resource: return TriggerResult(False,"invalid_event")
        except (ValueError,UnicodeDecodeError,json.JSONDecodeError): return TriggerResult(False,"invalid_event")
        stage,owner=self.store.begin(event_id,timestamp,payload)
        if stage in {"completed","ignored_wrong_study","stale","busy"}: return TriggerResult(True,stage)
        return self._process(event_id,payload,owner)
    def drain_pending(self):
        results=[]
        for event_id,payload in self.store.retryable():
            stage,owner=self.store.begin(event_id,int(payload.get("_ledger_timestamp",0)),payload)
            if owner: results.append(self._process(event_id,payload,owner))
        return results
    def periodic(self):
        drained=self.drain_pending(); report=self._run(); return {"status":report.get("status"),"report":report,"drained":len(drained)}
class _WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != self.path_config: self.send_error(404); return
        try: length=int(self.headers.get("Content-Length","-1"))
        except ValueError: length=-1
        if length<0 or length>1_000_000: self.send_error(400); return
        result=self.trigger.handle(self.rfile.read(length),dict(self.headers.items()),self.secret); self.send_response(202 if result.accepted else 401); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps({"status":result.status,"report":result.report}).encode())
    def log_message(self,*args): pass
def make_webhook_server(trigger,secret,host="127.0.0.1",port=0,path="/prolific/webhook"):
    handler=type("ConfiguredWebhookHandler",(_WebhookHandler,),{"trigger":trigger,"secret":secret,"path_config":path}); return ThreadingHTTPServer((host,port),handler)
def run_periodic(trigger,interval_seconds,stop,*,production_enabled=False):
    if production_enabled: raise ValueError("production execution is disabled")
    if interval_seconds<=0: raise ValueError("interval_seconds must be positive")
    while not stop.is_set(): trigger.periodic(); stop.wait(interval_seconds)
