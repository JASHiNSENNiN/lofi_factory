"""An offline YouTube API that checks every request against Google's own API
definition (the discovery documents googleapiclient ships with).

The client is built from the real document, so a wrong method or parameter
name fails here exactly as it would against YouTube. Requests never leave the
process: a fake transport answers them. Each request body is checked against
the document's schema: unknown fields, wrong types, fields the API reference
documents as read-only, and parts of the resource the request's `part=`
doesn't name (YouTube rejects those, or for update calls, deletes what's
left out). Violations are collected, not raised, because much of the code
under test deliberately swallows API errors.
"""
from __future__ import annotations

import json
import os
import threading
from urllib.parse import parse_qs, urlparse

import googleapiclient
import httplib2
from googleapiclient import http as gapi_http
from googleapiclient.discovery import build_from_document

_DOCS = os.path.join(os.path.dirname(googleapiclient.__file__), "discovery_cache", "documents")

# Read-only per the Data API reference (the discovery document doesn't mark
# them). Sending them is ignored at best; madeForKids silently left uploads
# without an audience declaration.
READ_ONLY = {
    ("Video", "status.madeForKids"), ("Video", "status.uploadStatus"),
    ("Video", "status.failureReason"), ("Video", "status.rejectionReason"),
    ("Video", "snippet.publishedAt"), ("Video", "snippet.channelId"),
    ("Video", "snippet.channelTitle"), ("Video", "snippet.thumbnails"),
    ("Video", "snippet.liveBroadcastContent"), ("Video", "snippet.localized"),
    ("LiveBroadcast", "status.lifeCycleStatus"), ("LiveBroadcast", "status.recordingStatus"),
    ("LiveBroadcast", "snippet.actualStartTime"), ("LiveBroadcast", "snippet.actualEndTime"),
    ("LiveBroadcast", "snippet.channelId"), ("LiveBroadcast", "snippet.publishedAt"),
    ("LiveStream", "status"),
}

_UNIVERSAL_ITEM = {
    "id": "item1",
    "kind": "youtube#video",
    "snippet": {"title": "a title", "description": "keep me", "tags": ["lofi"],
                "categoryId": "10", "scheduledStartTime": "2026-10-02T10:00:00Z",
                "defaultLanguage": "en", "publishedAt": "2026-09-01T00:00:00Z",
                "topLevelComment": {"id": "c1", "snippet": {"textDisplay": "hi",
                                                             "authorDisplayName": "a",
                                                             "publishedAt": "2026-09-01T00:00:00Z",
                                                             "likeCount": 0}},
                "totalReplyCount": 0, "videoId": "v1"},
    "status": {"privacyStatus": "private", "publishAt": "2026-10-03T08:00:00Z",
               "selfDeclaredMadeForKids": False, "license": "youtube",
               "streamStatus": "active", "lifeCycleStatus": "ready"},
    "statistics": {"viewCount": "10", "likeCount": "1", "commentCount": "0",
                   "subscriberCount": "5", "videoCount": "3"},
    "contentDetails": {"duration": "PT1H", "boundStreamId": "s1", "itemCount": 4,
                       "relatedPlaylists": {"uploads": "UU1"}},
    "cdn": {"ingestionInfo": {"ingestionAddress": "rtmp://a.rtmp.youtube.com/live2",
                              "streamName": "key-1"}},
}


def _json_or_none(body):
    """A request's JSON metadata; media uploads send image/video bytes."""
    if not body:
        return None
    try:
        out = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    return out if isinstance(out, dict) else None


def _response_for(method_id: str) -> dict:
    if method_id.startswith("youtubeAnalytics."):
        return {"columnHeaders": [{"name": "day"}, {"name": "views"}], "rows": []}
    if method_id.endswith(".list"):
        return {"items": [json.loads(json.dumps(_UNIVERSAL_ITEM))], "pageInfo": {"totalResults": 1}}
    if method_id == "youtube.search.list":
        return {"items": [{"id": {"videoId": "v1"}}]}
    return json.loads(json.dumps(_UNIVERSAL_ITEM))


class _Transport:
    """httplib2-compatible fake: answers every request, including the two
    steps of a resumable upload."""

    def __init__(self, recorder: "ContractRecorder"):
        self.rec = recorder

    def request(self, uri, method="GET", body=None, headers=None, **_):
        q = parse_qs(urlparse(uri).query)
        if q.get("uploadType") == ["resumable"] and method == "POST":
            return httplib2.Response({"status": "200", "location": "https://upload.local/session"}), b""
        if uri.startswith("https://upload.local/"):
            mid = "youtube.videos.insert"
        else:
            mid = getattr(self.rec._local, "method", "")
        content = json.dumps(_response_for(mid)).encode()
        return httplib2.Response({"status": "200", "content-type": "application/json"}), content


class ContractRecorder:
    def __init__(self):
        self.docs = {name: json.load(open(os.path.join(_DOCS, name + ".json")))
                     for name in ("youtube.v3", "youtubeAnalytics.v2")}
        self.calls: list[tuple[str, dict, dict | None]] = []
        self.violations: list[str] = []
        self._local = threading.local()   # each thread's request in flight
        self.transport = _Transport(self)

    # ── clients ─────────────────────────────────────────────────────────
    def client(self, api: str = "youtube", version: str = "v3"):
        return build_from_document(self.docs[f"{api}.{version}"], http=self.transport)

    def fake_build(self, api, version, *args, **kwargs):
        return self.client(api, version)

    # ── recording + checks ──────────────────────────────────────────────
    def record(self, req) -> None:
        mid = req.methodId
        self._local.method = mid
        q = {k: v[0] for k, v in parse_qs(urlparse(req.uri).query).items()}
        body = _json_or_none(req.body) or getattr(req, "_contract_body", None)
        self.calls.append((mid, q, body))
        if body is not None:
            self._check_body(mid, q, body)

    def _method_spec(self, mid: str) -> tuple[dict, dict]:
        api, *path = mid.split(".")
        doc = self.docs["youtube.v3" if api == "youtube" else "youtubeAnalytics.v2"]
        node = doc
        for name in path[:-1]:
            node = node["resources"][name]
        return doc, node["methods"][path[-1]]

    def _check_body(self, mid: str, q: dict, body: dict) -> None:
        doc, spec = self._method_spec(mid)
        ref = (spec.get("request") or {}).get("$ref")
        if not ref:
            return
        if "part" in spec.get("parameters", {}):
            parts = set((q.get("part") or "").split(","))
            extra = set(body) - parts - {"id", "kind", "etag"}
            if extra:
                self.violations.append(f"{mid}: body has {sorted(extra)} but part={q.get('part')!r}")
        self._walk(doc, ref, ref, body, "", mid)

    def _walk(self, doc, root, ref, value, path, mid):
        schema = doc["schemas"][ref]
        if not isinstance(value, dict):
            self.violations.append(f"{mid}: {root}.{path} should be an object")
            return
        props = schema.get("properties", {})
        for key, val in value.items():
            p = f"{path}.{key}" if path else key
            if key not in props:
                self.violations.append(f"{mid}: unknown field {root}.{p}")
                continue
            if (root, p) in READ_ONLY:
                self.violations.append(f"{mid}: read-only field {root}.{p} sent")
            self._check_value(doc, root, props[key], val, p, mid)

    def _check_value(self, doc, root, prop, val, p, mid):
        if "$ref" in prop:
            sub = doc["schemas"][prop["$ref"]]
            if sub.get("type") == "object" and "properties" in sub:
                self._walk_nested(doc, root, sub, val, p, mid)
            return
        t = prop.get("type")
        ok = {"string": isinstance(val, str), "boolean": isinstance(val, bool),
              "integer": isinstance(val, (int, str)) and not isinstance(val, bool),
              "number": isinstance(val, (int, float)), "array": isinstance(val, list),
              "object": isinstance(val, dict)}.get(t, True)
        if not ok:
            self.violations.append(f"{mid}: {root}.{p} should be {t}, got {type(val).__name__}")
        if t == "string" and "enum" in prop and val not in prop["enum"]:
            self.violations.append(f"{mid}: {root}.{p}={val!r} not in {prop['enum']}")
        if t == "array" and isinstance(val, list) and "items" in prop:
            for i, item in enumerate(val):
                self._check_value(doc, root, prop["items"], item, f"{p}[{i}]", mid)

    def _walk_nested(self, doc, root, schema, value, path, mid):
        if not isinstance(value, dict):
            self.violations.append(f"{mid}: {root}.{path} should be an object")
            return
        props = schema.get("properties", {})
        for key, val in value.items():
            p = f"{path}.{key}"
            if key not in props:
                self.violations.append(f"{mid}: unknown field {root}.{p}")
                continue
            if (root, p) in READ_ONLY:
                self.violations.append(f"{mid}: read-only field {root}.{p} sent")
            self._check_value(doc, root, props[key], val, p, mid)

    def methods(self) -> list[str]:
        return [c[0] for c in self.calls]


def install(monkeypatch) -> ContractRecorder:
    """Route every googleapiclient request in the process through a recorder."""
    rec = ContractRecorder()
    orig_execute = gapi_http.HttpRequest.execute
    orig_next_chunk = gapi_http.HttpRequest.next_chunk
    orig_init = gapi_http.HttpRequest.__init__

    def init(self, *a, **kw):
        orig_init(self, *a, **kw)
        # A resumable upload sends its metadata in the first request only.
        self._contract_body = _json_or_none(self.body)

    def execute(self, *a, **kw):
        rec.record(self)
        return orig_execute(self, *a, **kw)

    def next_chunk(self, *a, **kw):
        if not getattr(self, "_contract_seen", False):
            self._contract_seen = True
            rec.record(self)
        return orig_next_chunk(self, *a, **kw)

    monkeypatch.setattr(gapi_http.HttpRequest, "__init__", init)
    monkeypatch.setattr(gapi_http.HttpRequest, "execute", execute)
    monkeypatch.setattr(gapi_http.HttpRequest, "next_chunk", next_chunk)
    monkeypatch.setattr("googleapiclient.discovery.build", rec.fake_build)
    return rec
