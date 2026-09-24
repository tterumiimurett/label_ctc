#!/usr/bin/env python3
"""Serve blinded Clarification and Backchannel agreement batches."""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import tempfile
import os
from urllib.parse import parse_qs, urlparse


MAX_BODY_BYTES = 64 * 1024
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{16,128}")
KEY_RE = re.compile(r"[0-9a-f]{16}")


class Store:
    def __init__(self, dataset_dir: Path, data_dir: Path, annotators_path: Path):
        self.dataset_dir = dataset_dir.resolve()
        self.data_dir = data_dir.resolve()
        self.static_dir = Path(__file__).with_name("static").resolve()
        manifest = json.loads((self.dataset_dir / "tasks.json").read_text(encoding="utf-8"))
        self.tasks = manifest["cases"]
        self.task_by_key = {task["key"]: task for task in self.tasks}
        annotators = json.loads(annotators_path.read_text(encoding="utf-8"))
        self.annotators = {entry["token"]: entry.get("display_name", "Annotator") for entry in annotators["annotators"]}
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def valid_token(self, token: str) -> bool:
        return bool(TOKEN_RE.fullmatch(token)) and token in self.annotators

    def label_path(self, token: str, key: str) -> Path:
        return self.data_dir / "results" / token / f"{key}.json"

    def progress(self, token: str) -> dict:
        saved = [task["key"] for task in self.tasks if self.label_path(token, task["key"]).is_file()]
        return {"saved_keys": saved, "saved_count": len(saved), "total": len(self.tasks)}

    def save(self, token: str, key: str, payload: dict) -> Path:
        if key not in self.task_by_key or payload.get("key") != key:
            raise ValueError("unknown_case")
        task_type = self.task_by_key[key].get("task_type")
        if payload.get("task_type") != task_type:
            raise ValueError("invalid_task_type")
        if payload.get("turn_completion") not in ("yes", "no", "uncertain"):
            raise ValueError("invalid_target_behavior")
        if payload.get("natural_completion") not in ("yes", "no", "uncertain"):
            raise ValueError("invalid_natural")
        if payload.get("asr_quality") not in ("match", "minor", "material", "uncertain"):
            raise ValueError("invalid_asr_quality")
        for field in ("user_transcript", "model_transcript", "note"):
            if not isinstance(payload.get(field), str):
                raise ValueError(f"invalid_{field}")
        record = dict(payload)
        record["annotator_token"] = token
        destination = self.label_path(token, key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=destination.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(record, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, destination)
        return destination


def make_handler(store: Store):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LabConversationAgreement/1"

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/annotate"):
                return self.send_file(store.static_dir / "index.html", store.static_dir)
            if parsed.path == "/healthz":
                return self.send_json({"status": "ok", "task_count": len(store.tasks)})
            if parsed.path.startswith("/static/"):
                return self.send_file(store.static_dir / parsed.path.removeprefix("/static/"), store.static_dir)
            token = parse_qs(parsed.query).get("annotator", [""])[0]
            if not store.valid_token(token):
                return self.send_json({"error": "invalid_annotator_link"}, HTTPStatus.FORBIDDEN)
            if parsed.path == "/api/tasks":
                return self.send_json({"cases": store.tasks})
            if parsed.path == "/api/progress":
                return self.send_json(store.progress(token))
            if parsed.path.startswith("/api/label/"):
                key = parsed.path.removeprefix("/api/label/")
                if not KEY_RE.fullmatch(key) or key not in store.task_by_key:
                    return self.send_error(HTTPStatus.NOT_FOUND)
                path = store.label_path(token, key)
                if not path.is_file():
                    return self.send_json({"error": "no_saved_label"}, HTTPStatus.NOT_FOUND)
                return self.send_json(json.loads(path.read_text(encoding="utf-8")))
            if parsed.path.startswith("/audio/"):
                name = parsed.path.removeprefix("/audio/")
                if not re.fullmatch(r"[0-9a-f]{16}\.wav", name):
                    return self.send_error(HTTPStatus.NOT_FOUND)
                return self.send_file(store.dataset_dir / "audio" / name, store.dataset_dir / "audio")
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self):
            parsed = urlparse(self.path)
            if not parsed.path.startswith("/api/label/"):
                return self.send_error(HTTPStatus.NOT_FOUND)
            token = parse_qs(parsed.query).get("annotator", [""])[0]
            if not store.valid_token(token):
                return self.send_json({"error": "invalid_annotator_link"}, HTTPStatus.FORBIDDEN)
            key = parsed.path.removeprefix("/api/label/")
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 1 <= size <= MAX_BODY_BYTES:
                    raise ValueError("invalid_body_size")
                payload = json.loads(self.rfile.read(size))
                destination = store.save(token, key, payload)
            except (ValueError, json.JSONDecodeError) as error:
                return self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return self.send_json({"saved": True})

        def send_json(self, data: dict, status: HTTPStatus = HTTPStatus.OK):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_file(self, path: Path, allowed_root: Path):
            path = path.resolve()
            if not path.is_file() or (path != allowed_root and allowed_root not in path.parents):
                return self.send_error(HTTPStatus.NOT_FOUND)
            size = path.stat().st_size
            start, end, status = 0, size - 1, HTTPStatus.OK
            range_header = self.headers.get("Range")
            if range_header:
                match = re.fullmatch(r"bytes=(\d+)-(\d*)", range_header.strip())
                if not match:
                    return self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                start = int(match.group(1))
                end = min(int(match.group(2)), size - 1) if match.group(2) else size - 1
                if start >= size or end < start:
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                status = HTTPStatus.PARTIAL_CONTENT
            self.send_response(status)
            self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            with path.open("rb") as handle:
                handle.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = handle.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def log_message(self, format: str, *args):
            # Query strings contain private annotator tokens.
            return

    return Handler


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("lab_ctc_agreement_data"))
    parser.add_argument("--annotators", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main():
    args = parse_args()
    store = Store(args.dataset_dir, args.data_dir, args.annotators)
    print(f"Serving {len(store.tasks)} cases at http://{args.host}:{args.port}/annotate")
    ThreadingHTTPServer((args.host, args.port), make_handler(store)).serve_forever()


if __name__ == "__main__":
    main()
