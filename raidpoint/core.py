"""Núcleo compartilhado do Raid Point: projetos, eventos, memória, segredos, tmux (local/remoto)."""
import json, os, re, shlex, shutil, sqlite3, subprocess, time, uuid
from pathlib import Path

HOME = Path(os.environ.get("RAIDPOINT_HOME", Path.home() / ".raid_point"))
CFG = HOME                      # projects.json, agents.json, tmux.conf
DATA = HOME / "data"            # eventos, memória
WS = HOME / "workspaces"        # clones dos repositórios do GitHub: ~/.raid_point/workspaces/<repo>
EVENTS = DATA / "events.jsonl"
MEMDIR = DATA / "memory"
REQDIR = DATA / "req"
CM = HOME / "cache"
for _d in (DATA, MEMDIR, REQDIR, CM, WS):
    _d.mkdir(parents=True, exist_ok=True)
_defaults = Path(__file__).resolve().parent.parent / "config"
for _f in ("tmux.conf", "agents.json"):
    if not (CFG / _f).exists() and (_defaults / _f).exists():
        shutil.copy(_defaults / _f, CFG / _f)
TMUX = ["tmux", "-L", "tp", "-f", str(CFG / "tmux.conf")]

# ---------------------------------------------------------------- projetos
def load_projects():
    try:
        d = json.loads((CFG / "projects.json").read_text())
    except Exception:
        return {}
    return {k: v for k, v in d.items() if isinstance(v, dict)}

def agents_cfg():
    try:
        return json.loads((CFG / "agents.json").read_text())
    except Exception:
        return [{"name": "Shell", "cmd": ""}]

def project_for_cwd(cwd):
    """projeto cujo diretório contém cwd (o mais específico)"""
    best, blen = None, -1
    cwd = os.path.realpath(cwd or ".")
    for n, p in load_projects().items():
        if p.get("host"):
            continue
        d = os.path.realpath(os.path.expanduser(p.get("dir", "")))
        if d and (cwd == d or cwd.startswith(d + os.sep)) and len(d) > blen:
            best, blen = n, len(d)
    return best

def pdir(name):
    p = load_projects().get(name, {})
    return p.get("dir") if p.get("host") else os.path.expanduser(p.get("dir", "~"))

# ---------------------------------------------------------------- tmux
def run_tmux(project, *a, timeout=15):
    p = load_projects().get(project, {})
    if p.get("host"):
        cmd = ["ssh", "-o", "ControlMaster=auto", "-o", f"ControlPath={CM}/cm-%C", "-o", "ControlPersist=120",
               "-o", "BatchMode=yes", p["host"], shlex.join(["tmux", *a])]
    else:
        cmd = TMUX + list(a)
    try:
        return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    except Exception as e:
        return subprocess.CompletedProcess(cmd, 1, "", str(e))

PANE_FMT = "#{pane_id}\t#{pane_title}\t#{pane_current_command}\t#{pane_current_path}\t#{window_index}\t#{pane_active}\t#{pane_pid}\t#{t:window_activity}\t#{window_activity}"

def list_panes(project):
    r = run_tmux(project, "list-panes", "-s", "-t", project, "-F", PANE_FMT)
    out = []
    now = time.time()
    for l in r.stdout.splitlines():
        f = l.split("\t")
        if len(f) < 9: continue
        try: age = max(0, int(now - int(f[8])))
        except ValueError: age = 999
        out.append({"id": f[0], "title": f[1], "cmd": f[2], "path": f[3], "window": f[4],
                    "active": f[5] == "1", "pid": f[6], "idle_s": age})
    return out

def resolve_pane(project, target):
    ps = list_panes(project)
    for p in ps:
        if target in (p["id"], p["title"]): return p["id"]
    for p in ps:
        if target.lower() in p["title"].lower(): return p["id"]
    return None

def git_root(path):
    r = subprocess.run(["git", "-C", path, "rev-parse", "--show-toplevel"], text=True, capture_output=True)
    return r.stdout.strip() if r.returncode == 0 else None

def make_worktree(project, name):
    """cria um git worktree isolado para um agente; devolve o caminho (ou None)"""
    d = pdir(project)
    root = git_root(d) if d and not load_projects()[project].get("host") else None
    if not root: return None
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "agente"
    base = Path(root).parent / f"{Path(root).name}-wt"
    base.mkdir(exist_ok=True)
    for i in range(1, 100):
        path, br = base / f"{slug}-{i}", f"agent/{slug}-{i}"
        if not path.exists():
            r = subprocess.run(["git", "-C", root, "worktree", "add", "-b", br, str(path)], text=True, capture_output=True)
            return str(path) if r.returncode == 0 else None
    return None

def spawn_pane(project, title, cmd="", worktree=False, layout="tiled", cwd=None):
    d = cwd or pdir(project)
    if worktree and not cwd:
        d = make_worktree(project, title) or d
    a = ["split-window", "-t", project, "-P", "-F", "#{pane_id}"] + (["-c", d] if d else [])
    if cmd: a.append(cmd)
    pid = run_tmux(project, *a).stdout.strip()
    if pid:
        run_tmux(project, "select-pane", "-t", pid, "-T", title)
        run_tmux(project, "select-layout", "-t", project, layout)
    return pid, d

# ---------------------------------------------------------------- eventos
def log_event(ev):
    ev.setdefault("ts", time.time())
    with open(EVENTS, "a") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")

def read_events(max_age=6 * 3600, limit=4000):
    try: lines = EVENTS.read_text().splitlines()[-limit:]
    except FileNotFoundError: return []
    now = time.time(); out = []
    for l in lines:
        try: e = json.loads(l)
        except Exception: continue
        if now - e.get("ts", 0) <= max_age: out.append(e)
    return out

def sessions(project=None):
    """agrupa eventos em sessões de IA com subagentes: {sid: {...}}"""
    S = {}
    for e in read_events():
        sid = e.get("session_id")
        if not sid: continue
        if project and e.get("project") != project: continue
        s = S.setdefault(sid, {"id": sid, "harness": e.get("harness", "?"), "project": e.get("project"),
                               "cwd": e.get("cwd"), "start": e["ts"], "last": e["ts"], "status": "idle",
                               "transcript": e.get("transcript"), "subs": {}, "prompt": ""})
        s["last"] = e["ts"]; s["transcript"] = e.get("transcript") or s["transcript"]
        ev = e.get("event")
        if ev == "UserPromptSubmit": s["status"] = "working"; s["prompt"] = (e.get("prompt") or "")[:80]
        elif ev in ("Stop", "SessionEnd"): s["status"] = "idle" if ev == "Stop" else "ended"
        elif ev == "Notification": s["status"] = "waiting"
        elif ev == "SubagentStart":
            s["subs"][e.get("agent_id", "?")] = {"id": e.get("agent_id", "?"), "type": e.get("agent_type", "subagent"),
                                                "start": e["ts"], "end": None, "transcript": None}
        elif ev == "SubagentStop":
            a = s["subs"].setdefault(e.get("agent_id", "?"), {"id": e.get("agent_id", "?"),
                                     "type": e.get("agent_type", "subagent"), "start": e["ts"], "end": None, "transcript": None})
            a["end"] = e["ts"]; a["transcript"] = e.get("agent_transcript") or a["transcript"]
    return S

# ---------------------------------------------------------------- memória (markdown + índice FTS)
def _mdb():
    db = sqlite3.connect(DATA / "memory.db")
    db.execute("create virtual table if not exists mem using fts5(project, kind, tags, text, path unindexed, ts unindexed)")
    return db

def mem_add(project, text, kind="note", tags=""):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())[:40].strip("-") or "nota"
    d = MEMDIR / project; d.mkdir(parents=True, exist_ok=True)
    path = d / f"{time.strftime('%Y%m%d-%H%M%S')}-{slug}.md"
    path.write_text(f"---\nkind: {kind}\ntags: {tags}\nts: {ts}\n---\n\n{text}\n")
    with _mdb() as db:
        db.execute("insert into mem(project,kind,tags,text,path,ts) values (?,?,?,?,?,?)",
                   (project, kind, tags, text, str(path), ts))
    return str(path)

def mem_reindex():
    with _mdb() as db:
        db.execute("delete from mem")
        for f in sorted(MEMDIR.glob("*/*.md")):
            raw = f.read_text(); m = re.match(r"---\n(.*?)\n---\n\n(.*)", raw, re.S)
            meta = dict(l.split(": ", 1) for l in (m.group(1).splitlines() if m else []) if ": " in l)
            db.execute("insert into mem values (?,?,?,?,?,?)", (f.parent.name, meta.get("kind", "note"),
                       meta.get("tags", ""), (m.group(2) if m else raw).strip(), str(f), meta.get("ts", "")))

def mem_search(project, query, limit=8):
    q = " ".join(f'"{w}"' for w in re.findall(r"\w+", query))
    with _mdb() as db:
        if not q: return []
        rows = db.execute("select kind,tags,text,ts,path from mem where mem match ? and project = ? "
                          "order by bm25(mem) limit ?", (f"{q}", project, limit)).fetchall()
    return [dict(kind=r[0], tags=r[1], text=r[2], ts=r[3], path=r[4]) for r in rows]

def mem_recent(project, limit=8):
    with _mdb() as db:
        rows = db.execute("select kind,tags,text,ts,path from mem where project = ? order by ts desc limit ?",
                          (project, limit)).fetchall()
    return [dict(kind=r[0], tags=r[1], text=r[2], ts=r[3], path=r[4]) for r in rows]

# ---------------------------------------------------------------- segredos (chaveiro do sistema)
def _st(*a, inp=None):
    return subprocess.run(["secret-tool", *a], text=True, capture_output=True, input=inp)

def secret_set(project, name, value):
    r = _st("store", "--label", f"raidpoint:{project}:{name}", "service", "raidpoint", "project", project, "name", name, inp=value)
    return r.returncode == 0

def secret_get(project, name):
    r = _st("lookup", "service", "raidpoint", "project", project, "name", name)
    return r.stdout if r.returncode == 0 and r.stdout else None

def secret_rm(project, name):
    return _st("clear", "service", "raidpoint", "project", project, "name", name).returncode == 0

def secret_names(project):
    r = _st("search", "--all", "service", "raidpoint", "project", project)
    return sorted(set(re.findall(r"attribute\.name = (.+)", r.stdout + r.stderr)))

def redact(text, values):
    for v in sorted(values, key=len, reverse=True):
        if v and len(v) >= 4:
            text = text.replace(v, "«segredo»")
            text = text.replace(shlex.quote(v), "«segredo»")
    return text

def ask_approval(kind, project, detail, timeout=120):
    """pede aprovação humana ao app Raid Point (diálogo). Sem app rodando = negado."""
    rid = uuid.uuid4().hex[:10]
    f = REQDIR / f"{rid}.json"
    f.write_text(json.dumps({"id": rid, "kind": kind, "project": project, "detail": detail,
                             "status": "pending", "ts": time.time()}))
    t0 = time.time()
    while time.time() - t0 < timeout:
        try: st = json.loads(f.read_text()).get("status")
        except Exception: st = "pending"
        if st in ("approved", "denied"):
            f.unlink(missing_ok=True); return st == "approved"
        time.sleep(0.5)
    f.unlink(missing_ok=True)
    return False

def run_with_secrets(project, command, names, purpose=""):
    """roda um comando com segredos injetados em variáveis de ambiente; saída com segredos mascarados"""
    have = secret_names(project)
    missing = [n for n in names if n not in have]
    if missing: return {"error": f"segredos inexistentes: {missing}"}
    detail = f"Comando: {command}\nSegredos: {', '.join(names)}\nMotivo: {purpose or '(não informado)'}"
    if not ask_approval("secret", project, detail):
        return {"error": "negado pelo usuário (ou sem resposta em 120s)"}
    env = dict(os.environ); vals = []
    for n in names:
        v = secret_get(project, n); env[n] = v or ""; vals.append(v or "")
    try:
        r = subprocess.run(command, shell=True, cwd=pdir(project), env=env, text=True,
                           capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        return {"error": "timeout (300s)"}
    return {"exit": r.returncode, "stdout": redact(r.stdout, vals)[-20000:], "stderr": redact(r.stderr, vals)[-8000:]}


# ---------------------------------------------------------------- repositórios do GitHub (via gh)
def gh_ok():
    return bool(shutil.which("gh")) and subprocess.run(["gh", "auth", "status"], capture_output=True).returncode == 0

def gh_repos(force=False, ttl=300):
    """todos os repositórios do usuário e das orgs (cache de 5 min), mais recentes primeiro"""
    cache = CM / "gh-repos.json"
    if not force and cache.exists() and time.time() - cache.stat().st_mtime < ttl:
        try: return json.loads(cache.read_text())
        except Exception: pass
    owners = [None]
    r = subprocess.run(["gh", "api", "user/orgs", "--jq", ".[].login"], text=True, capture_output=True)
    if r.returncode == 0: owners += r.stdout.split()
    repos, seen = [], set()
    for o in owners:
        cmd = ["gh", "repo", "list"] + ([o] if o else []) + ["--limit", "300", "--no-archived", "--json",
               "name,nameWithOwner,description,isPrivate,pushedAt,url"]
        r = subprocess.run(cmd, text=True, capture_output=True, timeout=60)
        if r.returncode != 0: continue
        for x in json.loads(r.stdout):
            if x["nameWithOwner"] not in seen:
                seen.add(x["nameWithOwner"]); x["owner"] = x["nameWithOwner"].split("/")[0]; repos.append(x)
    if not repos and cache.exists():
        return json.loads(cache.read_text())
    repos.sort(key=lambda x: x.get("pushedAt") or "", reverse=True)
    cache.write_text(json.dumps(repos))
    return repos

def workspace_path(nwo):
    """~/.raid_point/workspaces/<repo> (se já existe outro repo com esse nome: <dono>-<repo>)"""
    owner, name = nwo.split("/", 1)
    p = WS / name
    if p.exists():
        r = subprocess.run(["git", "-C", str(p), "remote", "get-url", "origin"], text=True, capture_output=True)
        if nwo.lower() not in r.stdout.lower(): p = WS / f"{owner}-{name}"
    return p

def ensure_workspace(nwo):
    """clona o repo no workspace se ainda não existir; devolve (caminho, erro)"""
    p = workspace_path(nwo)
    if (p / ".git").exists(): return str(p), None
    r = subprocess.run(["gh", "repo", "clone", nwo, str(p)], text=True, capture_output=True)
    return (str(p), None) if r.returncode == 0 else (None, (r.stderr or r.stdout).strip()[-400:])
