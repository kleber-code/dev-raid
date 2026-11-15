"""Orchestrator providers: the AI you chat with in /dev/raid (see docs/orchestrator.md).

A provider turns what you type into an answer, and may expose a history and a list of pending approvals.
Two ship with the core:
- ``claude-code``: headless Claude Code (`claude -p`) with the `raidpoint` MCP tools, using your own login;
- ``http``: any service that speaks the small REST contract of docs/orchestrator.md (bearer token, no redirects,
  https unless loopback). The token comes from a private file or environment variable, never from the config.
"""
import json, os, re, shutil, subprocess, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from . import core

MAX_BODY = 2_000_000
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
LOOPBACK = {"localhost", "127.0.0.1", "::1"}


class ProviderError(Exception):
    pass


class Provider:
    name = "provider"
    def send(self, text, on_delta=None):
        """send what the user typed; returns the full answer. on_delta(str) is called for streamed pieces, if any."""
        raise NotImplementedError
    def history(self, limit=60):
        """[{"role": "user"|"assistant", "text": str, "ts": any}]"""
        return []
    def pending_approvals(self):
        """[{"id", "kind", "tool", "summary", "origin", "created"}]: things the AI asked a human to approve"""
        return []
    def decide(self, approval_id, approve):
        raise ProviderError("this provider has no approvals")


# ---------------------------------------------------------------- generic HTTP provider
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):       # a redirect would carry the bearer token to another host
        return None
_OPENER = urllib.request.build_opener(_NoRedirect)

def _clean(s, n=200):
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(s))[:n].strip()

class HttpProvider(Provider):
    def __init__(self, cfg, chat_timeout=600, timeout=20):
        u = urllib.parse.urlsplit((cfg.get("url") or "").strip())
        if u.scheme not in ("https", "http") or not u.hostname or u.username or u.password or u.query or u.fragment:
            raise ProviderError("orchestrator.url must be like https://host/api")
        if u.scheme == "http" and u.hostname not in LOOPBACK:
            raise ProviderError("orchestrator.url must use https (plain http only for localhost)")
        self.base = (u.scheme + "://" + u.netloc + u.path).rstrip("/")
        self.name = _clean(cfg.get("name") or u.hostname, 40)
        self._token_file, self._token_env = (cfg.get("token_file") or "").strip(), (cfg.get("token_env") or "").strip()
        self.chat_timeout, self.timeout = chat_timeout, timeout
        self._token()                                   # fail early if it is missing or unsafe

    def _token(self):
        if self._token_file:
            path = Path(self._token_file).expanduser()
            try:
                if path.stat().st_mode & 0o077:
                    raise ProviderError(f"{path} is readable by other users: run chmod 600 on it")
                tok = path.read_text().strip()
            except OSError as e:
                raise ProviderError(f"cannot read token_file: {e.strerror}")
        else:
            tok = os.environ.get(self._token_env, "").strip() if self._token_env else ""
        if not tok or re.search(r"[\x00-\x20\x7f]", tok):
            raise ProviderError("no usable token: set orchestrator.token_file (chmod 600) or orchestrator.token_env")
        return tok

    def _open(self, method, path, body=None, timeout=None, accept="application/json"):
        headers = {"Authorization": f"Bearer {self._token()}", "Accept": accept, "User-Agent": f"devraid/{core.VERSION}"}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode(); headers["Content-Type"] = "application/json"
        try:
            return _OPENER.open(urllib.request.Request(self.base + path, data=data, method=method, headers=headers),
                                timeout=timeout or self.timeout)
        except urllib.error.HTTPError as e:
            try: detail = _clean(json.loads(e.read(2000)).get("detail") or "")
            except Exception: detail = ""
            finally: e.close()
            raise ProviderError(f"HTTP {e.code}" + (f": {detail}" if detail else ""))
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            raise ProviderError(f"cannot reach the orchestrator: {_clean(getattr(e, 'reason', e))}")

    def _json(self, r):
        raw = r.read(MAX_BODY + 1)
        if len(raw) > MAX_BODY: raise ProviderError("response too large")
        try: obj = json.loads(raw)
        except ValueError: raise ProviderError("response is not JSON")
        if not isinstance(obj, dict): raise ProviderError("unexpected response")
        return obj

    def send(self, text, on_delta=None):
        with self._open("POST", "/chat", {"text": text}, self.chat_timeout, "text/event-stream, application/json") as r:
            if r.headers.get_content_type() != "text/event-stream":
                out = self._json(r).get("text")
                if not isinstance(out, str): raise ProviderError("response has no 'text'")
                return out
            parts, size = [], 0
            for raw in r:                                # SSE: `data: {"delta": "..."}` ... `data: {"done": true, "text": "..."}`
                size += len(raw)
                if size > MAX_BODY: raise ProviderError("response too large")
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"): continue
                try: ev = json.loads(line[5:])
                except ValueError: continue
                if not isinstance(ev, dict): continue
                if ev.get("error"): raise ProviderError(_clean(ev["error"]))
                if isinstance(ev.get("delta"), str):
                    parts.append(ev["delta"])
                    if on_delta: on_delta(ev["delta"])
                if ev.get("done"):
                    return ev["text"] if isinstance(ev.get("text"), str) else "".join(parts)
            raise ProviderError("stream ended before 'done'")

    def history(self, limit=60):
        with self._open("GET", f"/history?limit={max(1, min(int(limit), 200))}") as r:
            msgs = self._json(r).get("messages")
        return [{"role": m["role"], "text": m["text"], "ts": m.get("ts")} for m in msgs or []
                if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("text"), str)]

    def pending_approvals(self):
        with self._open("GET", "/approvals") as r:
            items = self._json(r).get("approvals")
        out = []
        for a in items or []:
            if isinstance(a, dict) and ID_RE.match(str(a.get("id", ""))):
                out.append({"id": str(a["id"]), **{k: _clean(a.get(k, ""), 300) for k in ("kind", "tool", "summary", "origin", "created")}})
        return out

    def decide(self, approval_id, approve):
        if not ID_RE.match(str(approval_id)): raise ProviderError("invalid approval id")
        with self._open("POST", f"/approvals/{approval_id}/decide", {"approve": bool(approve)}) as r:
            res = self._json(r)
        if res.get("ok") is False: raise ProviderError(_clean(res.get("error") or "could not decide"))


# ---------------------------------------------------------------- headless Claude Code
class ClaudeCodeProvider(Provider):
    name = "Claude Code"
    def __init__(self, project=None):
        self.session, self.log = None, []
        d = core.pdir(project) if project else None
        self.cwd = d if d and os.path.isdir(d) else str(Path.home())

    def send(self, text, on_delta=None):
        exe = shutil.which("claude")
        if not exe: raise ProviderError("the `claude` command was not found")
        cmd = [exe, "-p", "--output-format", "json", "--allowedTools", "mcp__raidpoint"]
        cmd += ["--resume", self.session] if self.session else ["--append-system-prompt", core.ORCHESTRATOR_PROMPT]
        try:
            r = subprocess.run(cmd, input=text, cwd=self.cwd, text=True, capture_output=True, timeout=900)
        except subprocess.TimeoutExpired:
            raise ProviderError("Claude Code did not answer within 15 minutes")
        try: out = json.loads(r.stdout)
        except ValueError: out = None
        if not isinstance(out, dict) or r.returncode != 0 or out.get("is_error"):
            raise ProviderError(_clean((out or {}).get("result") or r.stderr or f"claude exited with {r.returncode}"))
        if isinstance(out.get("session_id"), str): self.session = out["session_id"]
        answer = out.get("result") if isinstance(out.get("result"), str) else ""
        now = time.time()
        self.log += [{"role": "user", "text": text, "ts": now}, {"role": "assistant", "text": answer, "ts": now}]
        return answer

    def history(self, limit=60):
        return self.log[-limit:]


def get_provider(cfg=None, project=None):
    """the provider selected in config.toml ([orchestrator] provider = "claude-code" | "http")"""
    cfg = cfg if cfg is not None else core.load_config().get("orchestrator", {})
    kind = (cfg.get("provider") or "claude-code").strip()
    if kind == "http": return HttpProvider(cfg)
    if kind == "claude-code": return ClaudeCodeProvider(project)
    raise ProviderError(f"unknown orchestrator provider: {kind!r}")
