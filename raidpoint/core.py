"""Shared core of /dev/raid: projects, events, memory, secrets, tmux (local/remote)."""
import fcntl, json, os, re, shlex, shutil, sqlite3, subprocess, time, uuid
from pathlib import Path

HOME = Path(os.environ.get("RAIDPOINT_HOME", Path.home() / ".raid_point"))
CFG = HOME                      # projects.json, agents.json, tmux.conf
DATA = HOME / "data"            # events, memory
WS = HOME / "workspaces"        # GitHub repository clones: ~/.raid_point/workspaces/<repo>
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
SOCKET = os.environ.get("RAIDPOINT_SOCKET", "tp")   # tmux socket name (dedicated server, separate from your own tmux)
TMUX = ["tmux", "-L", SOCKET, "-f", str(CFG / "tmux.conf")]

# ---------------------------------------------------------------- projects
PROJ = CFG / "projects.json"

CONFIG_DEFAULT = {
    "terminal": {"font": "Noto Sans Mono 11", "zoom_step": 0.1, "theme": "Catppuccin Mocha",
                 "accent": "Theme default", "cursor": "Block", "cursor_blink": False},
    "window": {"sidebar_width": 190},
    "tools": {"editor": "nvim", "file_manager": "ranger"},
    "updates": {"auto": True},
    # what every agent is told about git: "push" (commit and push), "commit" (commit only) or "off"; `rules` is your own
    # extra text, added to every briefing (house rules: commit style, language, what never to touch...)
    "agents": {"git": "push", "rules": ""},
    # where project secrets live: "keyring" (Secret Service) or "file" (0600 files in ~/.raid_point/secrets, for servers
    # without a keyring). RAIDPOINT_SECRETS overrides it.
    "secrets": {"backend": "keyring"},
    # the AI you chat with: "claude-code" (headless Claude Code) or "http" (see docs/orchestrator.md)
    "orchestrator": {"provider": "claude-code", "url": "", "token_secret": "", "token_file": "", "token_env": ""},
    # GTK format: "<Alt>d", "<Control><Shift>p"...  ("" disables)
    "keys": {
        "palette": "<Alt>d", "settings": "<Alt>comma", "changes": "<Alt>g",
        "agents_panel": "<Alt>j", "sidebar": "<Alt>b", "chat": "<Alt>k",
        "editor": "<Alt>e", "files": "<Alt>f", "quick_open": "<Alt>p",
        "zoom_in": "<Control>plus", "zoom_out": "<Control>minus", "zoom_reset": "<Control>0",
        "copy": "<Control><Shift>c", "paste": "<Control><Shift>v",
    },
}

THEMES = {   # background, foreground, 16 colors
    "Catppuccin Mocha": ("#1e1e2e", "#cdd6f4", "#45475a #f38ba8 #a6e3a1 #f9e2af #89b4fa #f5c2e7 #94e2d5 #bac2de "
                                                "#585b70 #f38ba8 #a6e3a1 #f9e2af #89b4fa #f5c2e7 #94e2d5 #a6adc8"),
    "Tokyo Night": ("#1a1b26", "#c0caf5", "#15161e #f7768e #9ece6a #e0af68 #7aa2f7 #bb9af7 #7dcfff #a9b1d6 "
                                          "#414868 #f7768e #9ece6a #e0af68 #7aa2f7 #bb9af7 #7dcfff #c0caf5"),
    "Gruvbox Dark": ("#282828", "#ebdbb2", "#282828 #cc241d #98971a #d79921 #458588 #b16286 #689d6a #a89984 "
                                           "#928374 #fb4934 #b8bb26 #fabd2f #83a598 #d3869b #8ec07c #ebdbb2"),
    "Nord": ("#2e3440", "#d8dee9", "#3b4252 #bf616a #a3be8c #ebcb8b #81a1c1 #b48ead #88c0d0 #e5e9f0 "
                                   "#4c566a #bf616a #a3be8c #ebcb8b #81a1c1 #b48ead #8fbcbb #eceff4"),
    "Satela Ember": ("#141418", "#e8e6e3", "#1d1d22 #e5534b #82c9a1 #f0b27a #7aa7f0 #c79bf0 #6fd0d0 #e8e6e3 "
                                           "#5b5b66 #ff6b63 #9fe0ba #ffc896 #9bc0ff #dcb5ff #8fe6e6 #ffffff"),
}

# INTERFACE colors per theme (the terminal uses THEMES). Keys: background, panel, dark border, lines, gray, text, accent, ...
THEME_UI = {
    "Catppuccin Mocha": dict(bg="#1e1e2e", mantle="#181825", crust="#11111b", s0="#313244", s1="#45475a", overlay="#6c7086",
                             text="#cdd6f4", accent="#cba6f7", green="#a6e3a1", red="#f38ba8", yellow="#f9e2af", blue="#89b4fa"),
    "Tokyo Night":      dict(bg="#1a1b26", mantle="#16161e", crust="#101014", s0="#292e42", s1="#3b4261", overlay="#565f89",
                             text="#c0caf5", accent="#bb9af7", green="#9ece6a", red="#f7768e", yellow="#e0af68", blue="#7aa2f7"),
    "Gruvbox Dark":     dict(bg="#282828", mantle="#1d2021", crust="#171717", s0="#3c3836", s1="#504945", overlay="#7c6f64",
                             text="#ebdbb2", accent="#d3869b", green="#b8bb26", red="#fb4934", yellow="#fabd2f", blue="#83a598"),
    "Nord":             dict(bg="#2e3440", mantle="#272c36", crust="#20242d", s0="#3b4252", s1="#434c5e", overlay="#616e88",
                             text="#d8dee9", accent="#b48ead", green="#a3be8c", red="#bf616a", yellow="#ebcb8b", blue="#81a1c1"),
    "Satela Ember":     dict(bg="#141418", mantle="#101013", crust="#0a0a0c", s0="#24242b", s1="#34343d", overlay="#6b6a72",
                             text="#e8e6e3", accent="#f0883e", green="#82c9a1", red="#e5534b", yellow="#f2d36b", blue="#7aa7f0"),
}
ACCENTS = {"Theme default": None, "Blue": "blue", "Green": "green", "Yellow": "yellow", "Red": "red"}
CURSORS = ["Block", "Bar", "Underline"]
# values stored by older (Portuguese) versions in config.toml -> current names
_LEGACY_TERMINAL = {
    "accent": {"Padr\u00e3o do tema": "Theme default", "Azul": "Blue", "Verde": "Green", "Amarelo": "Yellow", "Vermelho": "Red"},
    "cursor": {"Bloco": "Block", "Barra": "Bar", "Sublinhado": "Underline"},
}

def _mix(a, b, t):
    """blend two #rrggbb colors: t=0 -> a, t=1 -> b"""
    x = [int(a[i:i + 2], 16) for i in (1, 3, 5)]; y = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(p + (q - p) * t):02x}" for p, q in zip(x, y))

def ui_colors(term_cfg):
    """interface palette for the chosen theme and accent color"""
    ui = dict(THEME_UI.get(term_cfg.get("theme"), THEME_UI["Catppuccin Mocha"]))
    k = ACCENTS.get(term_cfg.get("accent"))
    if k: ui["accent"] = ui[k]
    return ui

def css_for(css_base, ui):
    """rewrite the default CSS colors (Catppuccin) to the `ui` palette in a single pass (no chained replacements)"""
    d = THEME_UI["Catppuccin Mocha"]
    m = {d[k]: ui[k] for k in d}
    if ui["bg"] != d["bg"]:                              # derived colors; the default theme keeps the original CSS
        m["#a6adc8"] = _mix(ui["text"], ui["bg"], .28)   # secondary text
        m["#585b70"] = ui["s1"]
    if ui["accent"] != d["accent"]:
        m["#d9bdfa"] = _mix(ui["accent"], "#ffffff", .22)  # accent on hover
    return re.sub(r"#[0-9a-fA-F]{6}", lambda mo: m.get(mo.group(0).lower(), mo.group(0)), css_base)

def _toml_val(v):
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, (int, float)): return repr(v)
    return json.dumps(str(v), ensure_ascii=False)

def save_config(cfg):
    """write ~/.raid_point/config.toml (atomically)"""
    lines = ["# /dev/raid — settings. You can edit this by hand, but the Settings panel (Ctrl+,) does it for you.", ""]
    for sec, vals in cfg.items():
        if not isinstance(vals, dict): continue
        lines.append(f"[{sec}]")
        lines += [f"{k} = {_toml_val(v)}" for k, v in vals.items()]
        lines.append("")
    f = HOME / "config.toml"; tmp = Path(str(f) + ".tmp")
    HOME.mkdir(parents=True, exist_ok=True)
    tmp.write_text("\n".join(lines)); os.replace(tmp, f)

def load_config():
    """config.toml merged with the defaults; creates the file the first time."""
    import copy, tomllib
    base = copy.deepcopy(CONFIG_DEFAULT)
    f = HOME / "config.toml"
    if not f.exists():
        try: save_config(base)
        except OSError: pass
        return base
    try: user = tomllib.loads(f.read_text())
    except Exception as e:
        print("warning: invalid config.toml, using defaults:", e, file=__import__("sys").stderr); user = {}
    for sec, vals in user.items():
        if isinstance(vals, dict): base.setdefault(sec, {}).update(vals)
    term = base.get("terminal", {})
    for k, legacy in _LEGACY_TERMINAL.items():            # migrate old Portuguese values (in memory)
        if term.get(k) in legacy: term[k] = legacy[term[k]]
    return base

def save_agents(lst):
    clean = [{"name": a["name"].strip(), "cmd": a.get("cmd", "").strip()} for a in lst if a.get("name", "").strip()]
    write_json_atomic(CFG / "agents.json", clean or [{"name": "Shell", "cmd": ""}])


def _parse_projects(text):
    """projects.json JSON; tolerates a trailing comma at the end of an object/list (common hand-editing mistake)"""
    try: return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(re.sub(r",(\s*[}\]])", r"\1", text))      # if it still fails, raises the original error

def projects_error():
    """None if projects.json is fine (or missing); otherwise the error message"""
    try: _parse_projects(PROJ.read_text()); return None
    except FileNotFoundError: return None
    except Exception as e: return f"{type(e).__name__}: {e}"

def read_projects():
    """raw projects.json content (includes metadata like _last); {} if missing or unreadable (for readers)"""
    try: return _parse_projects(PROJ.read_text())
    except Exception: return {}

def load_projects():
    return {k: v for k, v in read_projects().items() if isinstance(v, dict)}

def ordered_projects():
    """project names with pinned projects first, preserving relative order"""
    db = load_projects()
    return [n for n, p in db.items() if p.get("pinned")] + [n for n, p in db.items() if not p.get("pinned")]

def pin_project(name, pinned=True):
    def fn(db):
        if name not in db or not isinstance(db[name], dict): raise KeyError(name)
        if pinned: db[name]["pinned"] = True
        else: db[name].pop("pinned", None)
    update_projects(fn)

def set_project_note(name, note):
    note = (note or "").strip()
    def fn(db):
        if name not in db or not isinstance(db[name], dict): raise KeyError(name)
        if note: db[name]["note"] = note
        else: db[name].pop("note", None)
    update_projects(fn)

def update_projects(fn):
    """read-modify-write projects.json with a lock and an atomic write. If the file exists but is
    unreadable, it does NOT write (avoids wiping the whole list because of a bad read)."""
    with open(CFG / "projects.lock", "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try: d = _parse_projects(PROJ.read_text())
        except FileNotFoundError: d = {}
        r = fn(d)
        tmp = PROJ.with_suffix(".tmp"); tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False))
        os.replace(tmp, PROJ)
        return r if r is not None else d

def safe_name(s):
    """safe project name: no slashes/odd characters and not starting with '_' (reserved for metadata)"""
    return re.sub(r"[^\w .-]", "-", s or "").strip(" ._-") or "project"

def unique_name(base, taken_dir=None):
    """name that does not collide with another project in a different folder"""
    db = load_projects(); n, i = base, 2
    while n in db and (taken_dir is None or os.path.realpath(os.path.expanduser(db[n].get("dir", ""))) != os.path.realpath(taken_dir) or db[n].get("host")):
        n = f"{base}-{i}"; i += 1
    return n

def write_json_atomic(path, obj):
    tmp = Path(str(path) + ".tmp"); tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False)); os.replace(tmp, path)

def agents_cfg():
    try:
        return json.loads((CFG / "agents.json").read_text())
    except Exception:
        return [{"name": "Shell", "cmd": ""}]

def project_for_cwd(cwd):
    """project whose directory contains cwd (the most specific one)"""
    best, blen = None, -1
    cwd = os.path.realpath(cwd or ".")
    for n, p in load_projects().items():
        if p.get("host"):
            continue
        d = os.path.realpath(os.path.expanduser(p.get("dir", "")))
        for base in ((d, d + "-wt") if d else ()):             # <dir>-wt = agent worktrees
            if (cwd == base or cwd.startswith(base + os.sep)) and len(d) > blen:
                best, blen = n, len(d)
    return best

def pdir(name):
    p = load_projects().get(name, {})
    return p.get("dir") if p.get("host") else os.path.expanduser(p.get("dir", "~"))

# ---------------------------------------------------------------- tmux
def sess(name):
    """tmux session name of the project ('.' and ':' cannot be addressed by tmux)"""
    return re.sub(r"[.:]", "_", name)

def tgt(name):
    """EXACT window/pane target of the project session (without '=' tmux matches by prefix: 'api' would match 'api2')"""
    return f"={sess(name)}:"

def sess_t(name):
    """exact session target (kill-session, has-session, attach...)"""
    return f"={sess(name)}"

def _q(args):
    """join args for the remote shell, ALWAYS quoted (an unquoted '=name' would be expanded by zsh)"""
    return " ".join("'" + str(x).replace("'", "'\\''") + "'" for x in args)

def tmux_local(*a, timeout=15):
    try: return subprocess.run(TMUX + list(a), text=True, capture_output=True, timeout=timeout)
    except Exception as e: return subprocess.CompletedProcess(TMUX + list(a), 1, "", str(e))

def alive():
    r = tmux_local("list-sessions", "-F", "#{session_name}")
    return set(r.stdout.split("\n")) - {""} if r.returncode == 0 else set()

def ssh_hosts():
    hs = []
    try:
        for l in open(os.path.expanduser("~/.ssh/config")):
            m = re.match(r"\s*Host\s+(.+)", l, re.I)
            if m:
                hs += [h for h in m.group(1).split() if not re.search(r"[*?!]", h) and h != "github.com"]
    except Exception: pass
    return sorted(set(hs))

def remote_argv(name, p):
    """command that connects (mosh/ssh) to the remote project's tmux session"""
    tm = ["tmux", "new-session", "-A", "-s", sess(name)] + (["-c", p["dir"]] if p.get("dir") else []) + \
         [";", "set", "-g", "mouse", "on", ";", "set", "-g", "allow-set-title", "off",
          ";", "set", "-g", "pane-border-status", "top",
          ";", "set", "-g", "pane-border-format", " #{pane_title} "]
    if p.get("transport", "mosh") == "mosh" and shutil.which("mosh"):
        return ["mosh", p["host"], "--"] + tm
    return ["ssh", "-t", p["host"], _q(tm)]

def run_tmux(project, *a, timeout=15):
    p = load_projects().get(project, {})
    if p.get("host"):
        cmd = ["ssh", "-o", "ControlMaster=auto", "-o", f"ControlPath={CM}/cm-%C", "-o", "ControlPersist=120",
               "-o", "BatchMode=yes", p["host"], _q(["tmux", *a])]
    else:
        cmd = TMUX + list(a)
    try:
        return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    except Exception as e:
        return subprocess.CompletedProcess(cmd, 1, "", str(e))

import socket as _socket
_HOSTS = {_socket.gethostname(), _socket.gethostname().split(".")[0]}
PANE_FMT = "#{pane_id}\t#{pane_title}\t#{pane_current_command}\t#{pane_current_path}\t#{window_index}\t#{pane_active}\t#{pane_pid}\t#{t:window_activity}\t#{window_activity}"

def list_panes(project):
    r = run_tmux(project, "list-panes", "-s", "-t", tgt(project), "-F", PANE_FMT)
    out = []
    now = time.time()
    for l in r.stdout.splitlines():
        f = l.split("\t")
        if len(f) < 9: continue
        try: age = max(0, int(now - int(f[8])))
        except ValueError: age = 999
        if f[1] in _HOSTS: f[1] = "Shell"           # default tmux title = hostname
        out.append({"id": f[0], "title": f[1], "cmd": f[2], "path": f[3], "window": f[4],
                    "active": f[5] == "1", "pid": f[6], "idle_s": age})
    return out

# ---------------------------------------------------------------- sessions (the Sessions tab)
SESS_FMT = "#{session_name}\t#{session_windows}\t#{session_attached}\t#{session_created}\t#{session_activity}"
SESS_PANE_FMT = "#{session_name}\t#{pane_current_command}\t#{pane_current_path}\t#{window_index}"
SHELLS = {"bash", "zsh", "fish", "sh", "dash", "ksh", "nu", "tmux", "login", "-bash", "-zsh", "-fish"}

def parse_sessions(sess_out, panes_out, now=None):
    """tmux output -> [{name, windows, attached, created, activity, panes, busy:[commands], cwd, state}]
    state: 'open' (a client is attached) | 'busy' (detached, something running) | 'idle' (detached, only shells)"""
    now = now or time.time(); by = {}
    for l in sess_out.splitlines():
        f = l.split("\t")
        if len(f) < 5: continue
        try: w, a, c, act = int(f[1]), int(f[2]), int(f[3]), int(f[4])
        except ValueError: continue
        by[f[0]] = {"name": f[0], "windows": w, "attached": a, "created": c, "activity": act,
                    "panes": 0, "busy": [], "cwd": "", "age_s": max(0, int(now - act))}
    for l in panes_out.splitlines():
        f = l.split("\t")
        if len(f) < 4 or f[0] not in by: continue
        d = by[f[0]]; d["panes"] += 1
        if not d["cwd"]: d["cwd"] = f[2]
        cmd = f[1].strip()
        if cmd and cmd not in SHELLS and cmd not in d["busy"]: d["busy"].append(cmd)
    for d in by.values():
        d["state"] = "open" if d["attached"] else ("busy" if d["busy"] else "idle")
    return sorted(by.values(), key=lambda d: d["name"].lower())

def sessions_info():
    s = tmux_local("list-sessions", "-F", SESS_FMT)
    if s.returncode != 0: return []                     # no tmux server running = no sessions
    p = tmux_local("list-panes", "-a", "-F", SESS_PANE_FMT)
    return parse_sessions(s.stdout, p.stdout if p.returncode == 0 else "")

def kill_session(name):
    return tmux_local("kill-session", "-t", f"={name}").returncode == 0

def dur_short(sec):
    return "now" if sec < 10 else (f"{sec}s" if sec < 60 else (f"{sec // 60}m" if sec < 3600 else
           (f"{sec // 3600}h" if sec < 86400 else f"{sec // 86400}d")))

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
    """create an isolated git worktree for an agent; returns (path, error)"""
    p = load_projects().get(project, {})
    if p.get("host"): return None, "isolated worktrees do not work on remote projects"
    root = git_root(pdir(project) or "")
    if not root: return None, "the project is not a git repository"
    if subprocess.run(["git", "-C", root, "rev-parse", "--verify", "-q", "HEAD"], capture_output=True).returncode != 0:
        return None, "the repository has no commits yet (the worktree needs one)"
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "agent"
    base = Path(root).parent / f"{Path(root).name}-wt"
    base.mkdir(exist_ok=True)
    for i in range(1, 200):
        path, br = base / f"{slug}-{i}", f"agent/{slug}-{i}"
        if path.exists() or subprocess.run(["git", "-C", root, "show-ref", "--verify", "-q", f"refs/heads/{br}"],
                                           capture_output=True).returncode == 0:
            continue                                             # path or branch already taken: try the next number
        r = subprocess.run(["git", "-C", root, "worktree", "add", "-b", br, str(path)], text=True, capture_output=True)
        return (str(path), None) if r.returncode == 0 else (None, (r.stderr or r.stdout).strip()[-300:])
    return None, "too many worktrees (limit of 200 per agent)"

def agent_shell_cmd(cmd):
    """Run cmd inside an interactive login shell so the user's PATH (~/.local/bin, nvm, etc.)
    is loaded even when the tmux server was started from a desktop launcher with a minimal PATH.
    When the agent exits (or isn't installed), the pane drops into a shell instead of vanishing."""
    sh = '"${SHELL:-/bin/sh}"'
    return f"{sh} -lic {shlex.quote(cmd)}; exec {sh} -l"

def spawn_pane(project, title, cmd="", worktree=False, layout="tiled", cwd=None):
    """open a pane; returns (pane_id, folder, error). If a worktree was requested and it fails, it does NOT open (never run without isolation)"""
    d = cwd or pdir(project)
    if worktree and not cwd:
        d, err = make_worktree(project, title)
        if err: return None, None, f"worktree: {err}"
    a = ["split-window", "-t", tgt(project), "-P", "-F", "#{pane_id}"] + (["-c", d] if d else [])
    if cmd: a.append(agent_shell_cmd(cmd))
    r = run_tmux(project, *a)
    pid = r.stdout.strip()
    if not pid: return None, d, (r.stderr or "tmux did not create the pane").strip()[-200:]
    run_tmux(project, "select-pane", "-t", pid, "-T", title)
    run_tmux(project, "select-layout", "-t", tgt(project), layout)
    return pid, d, None

# ---------------------------------------------------------------- running without the app (servers)
def headless():
    """True on an install without the GTK app (install.sh --headless) or with RAIDPOINT_HEADLESS=1"""
    return os.environ.get("RAIDPOINT_HEADLESS") == "1" or not (Path(__file__).resolve().parent.parent / "bin" / "devraid-gui").exists()

def startup_cmd(project, entry):
    """a project `startup` entry -> (pane title, command): an agent preset name (agents.json) or a raw command"""
    entry = str(entry).strip()
    ag = {a["name"].lower(): a for a in agents_cfg()}.get(entry.lower())
    if ag: return ag["name"], agent_launch_cmd(ag, "", project)[0]
    try: title = os.path.basename(shlex.split(entry)[0])
    except (ValueError, IndexError): title = "startup"
    return title, entry

def up(names=None, everything=False):
    """start (detached) the tmux sessions that should be running, each with its `startup` panes: the projects in `names`,
    or every local project with a `startup` list or "autostart": true (everything=True: all local projects).
    Sessions already running are left alone. Returns [(project, status)]."""
    on = alive(); out = []
    for n, p in load_projects().items():
        st = [e for e in (p.get("startup") or []) if str(e).strip()]
        if names:
            if n not in names: continue
        elif p.get("host") or not (everything or st or p.get("autostart")) or (p.get("term") and not st): continue
        if p.get("host"): out.append((n, "skipped: remote project")); continue
        if sess(n) in on: out.append((n, "already running")); continue
        d = os.path.expanduser(p.get("dir") or "~")
        if not os.path.isdir(d): out.append((n, f"skipped: folder not found ({d})")); continue
        first = startup_cmd(n, st[0]) if st else None
        a = ["new-session", "-d", "-s", sess(n), "-c", d] + ([agent_shell_cmd(first[1])] if first and first[1] else [])
        r = tmux_local(*a)
        if r.returncode != 0: out.append((n, "failed: " + (r.stderr or "tmux").strip()[-160:])); continue
        if first: tmux_local("select-pane", "-t", tgt(n), "-T", first[0])
        errs = []
        for e in st[1:]:
            title, cmd = startup_cmd(n, e)
            if not spawn_pane(n, title, cmd)[0]: errs.append(title)
        out.append((n, f"started ({len(st)} startup pane(s))" + (f"; could not open: {', '.join(errs)}" if errs else "")))
    for n in (names or []):
        if n not in load_projects(): out.append((n, "unknown project"))
    return out

# ---------------------------------------------------------------- terminal editor (nvim/micro) & file manager (ranger/nnn)
EDITORS = ["nvim", "micro", "hx", "vim", "nano"]
FILE_MANAGERS = ["ranger", "nnn", "yazi", "lf"]

def configured_editor(cfg=None):
    cfg = cfg if cfg is not None else load_config()
    ed = (cfg.get("tools", {}).get("editor") or "nvim").strip()
    exe = shlex.split(ed)[0] if ed else "nvim"
    if shutil.which(exe):
        return ed
    for cand in EDITORS:
        if shutil.which(cand):
            return cand
    return ed or "nvim"

def configured_file_manager(cfg=None):
    cfg = cfg if cfg is not None else load_config()
    fm = (cfg.get("tools", {}).get("file_manager") or "ranger").strip()
    exe = shlex.split(fm)[0] if fm else "ranger"
    if shutil.which(exe):
        return fm
    for cand in FILE_MANAGERS:
        if shutil.which(cand):
            return cand
    return fm or "ranger"

def editor_cmd(filepath=None, line=None, cfg=None):
    """Build the command to open `filepath` (optionally at `line`) in the configured terminal editor (nvim/micro/etc.)."""
    ed = configured_editor(cfg)
    base = os.path.basename(shlex.split(ed)[0]) if ed else "nvim"
    env_prefix = f"EDITOR={shlex.quote(ed)} VISUAL={shlex.quote(ed)} "
    if not filepath:
        return env_prefix + (f"{ed} ." if base in ("nvim", "vim", "hx") else ed)
    qpath = shlex.quote(str(filepath))
    if line and int(line) > 0:
        ln = int(line)
        if base == "micro":
            return f"{env_prefix}{ed} +{ln}:1 {qpath}"
        if base in ("hx", "helix"):
            return f"{env_prefix}{ed} {shlex.quote(f'{filepath}:{ln}')}"
        return f"{env_prefix}{ed} +{ln} {qpath}"
    return f"{env_prefix}{ed} {qpath}"

def file_manager_cmd(target_dir=None, cfg=None):
    """Build the command to launch ranger/nnn with EDITOR and VISUAL set to the configured editor."""
    fm = configured_file_manager(cfg)
    ed = configured_editor(cfg)
    base_fm = os.path.basename(shlex.split(fm)[0]) if fm else "ranger"
    # For nnn, -e opens text files in $VISUAL/$EDITOR (nvim/micro) instead of xdg-open
    extra = " -e" if base_fm == "nnn" and " -e" not in fm else ""
    dir_arg = f" {shlex.quote(str(target_dir))}" if target_dir else ""
    return f"EDITOR={shlex.quote(ed)} VISUAL={shlex.quote(ed)} {fm}{extra}{dir_arg}"

def open_in_tmux_editor(project, filepath=None, line=None, cwd=None, layout="tiled", cfg=None):
    """Open `filepath` (or the project folder) in the configured terminal editor inside a tmux pane."""
    ed = configured_editor(cfg)
    ed_name = os.path.basename(shlex.split(ed)[0]) if ed else "editor"
    title = f"{ed_name}: {os.path.basename(filepath)}" if filepath else ed_name
    d = cwd or (os.path.dirname(os.path.abspath(filepath)) if filepath else pdir(project))
    cmd = editor_cmd(filepath, line, cfg)
    return spawn_pane(project, title, cmd, worktree=False, layout=layout, cwd=d)

def open_in_tmux_fm(project, cwd=None, layout="tiled", cfg=None, wt_label=None):
    """Open (or focus an existing) ranger/nnn file navigator pane in the project or worktree."""
    fm = configured_file_manager(cfg)
    fm_name = os.path.basename(shlex.split(fm)[0]) if fm else "files"
    title = f"{fm_name} [{wt_label}]" if wt_label and wt_label != "main" else fm_name
    # If an identical file-manager pane is already open in this project, focus it
    for p in list_panes(project):
        if p["title"] == title and p["cmd"] == fm_name:
            run_tmux(project, "select-window", "-t", f"={sess(project)}:{p['window']}")
            run_tmux(project, "select-pane", "-t", p["id"])
            return p["id"], p["path"], None
    d = cwd or pdir(project)
    cmd = file_manager_cmd(None, cfg)
    return spawn_pane(project, title, cmd, worktree=False, layout=layout, cwd=d)

# ---------------------------------------------------------------- orchestration
PROMPT_ARG = {"claude", "agy", "codex", "gemini", "cursor-agent", "opencode"}   # CLIs that accept the task as an initial argument

def _agy_has_hooks():
    """True when ~/.gemini/config/hooks.json has an enabled raidpoint hook"""
    try:
        d = json.loads((Path.home() / ".gemini" / "config" / "hooks.json").read_text())
        rp = d.get("raidpoint")
        return isinstance(rp, dict) and rp.get("enabled", True) is not False and bool(rp.get("SessionStart"))
    except Exception:
        return False

def agent_launch_cmd(ag, prompt="", project=None):
    """(command, needs_send_keys). Claude/Agy/Codex & co. get the task as an argument (reliable);
    the others start empty and the task is sent via send-keys afterwards. A preset can force it with "prompt": "arg"|"keys".
    With `project`, an agent WITHOUT hooks (Codex, Gemini, Aider, or agy without hooks) is pointed at the project briefing;
    Claude Code (and agy with hooks) get it through the SessionStart hook instead."""
    cmd = (ag.get("cmd") or "").strip()
    if not cmd: return cmd, False
    mode = ag.get("prompt")
    try: first = os.path.basename(shlex.split(cmd)[0])
    except (ValueError, IndexError): first = ""
    takes_arg = mode == "arg" or (mode is None and first in PROMPT_ARG)
    has_hook = first == "claude" or (first == "agy" and _agy_has_hooks())
    if project and not has_hook and not load_projects().get(project, {}).get("host"):
        try:
            f = write_briefing(project)
            if first == "aider": cmd = f"{cmd} --read {shlex.quote(str(f))}"      # read-only context file
            elif takes_arg:
                intro = (f"You are running inside /dev/raid. First read {f} (the project briefing: your tools, the project context "
                         "and its memory)")
                prompt = intro + (f", then do this task:\n\n{prompt}" if prompt else ", then wait for my instructions.")
        except Exception:
            pass                                                  # a briefing problem must never block opening the agent
    if not prompt: return cmd, False
    if takes_arg:
        if first == "agy":
            return f"{cmd} -i {shlex.quote(prompt)}", False
        return f"{cmd} {shlex.quote(prompt)}", False
    return cmd, True

def run_task(project, prompt, agents, worktree=True, layout="tiled"):
    """launch the SAME task on several agents, each (optionally) in an isolated worktree.
    agents: list of preset names (repeating a name = more copies). Returns [{agent, pane, dir, error}]."""
    presets = {a["name"].lower(): a for a in agents_cfg()}
    out = []
    for name in agents:
        ag = presets.get(name.lower())
        if not ag or not ag.get("cmd"):
            out.append({"agent": name, "pane": None, "dir": None, "error": "unknown preset or preset without a command"}); continue
        cmd, keys = agent_launch_cmd(ag, prompt, project)
        pid, d, err = spawn_pane(project, ag["name"], cmd, worktree, layout)
        if pid and keys:
            time.sleep(4)
            run_tmux(project, "send-keys", "-t", pid, "-l", prompt); run_tmux(project, "send-keys", "-t", pid, "Enter")
        out.append({"agent": ag["name"], "pane": pid, "dir": d, "error": err})
    return out

ORCHESTRATOR_PROMPT = (
    "You are the ORCHESTRATOR of this project in /dev/raid. When I give you a task: "
    "1) split it into independent parts (that do not edit the same files); "
    "2) for each part, use the `spawn_agent` MCP tool from the `raidpoint` server with worktree=true and the part's "
    "instructions in `prompt`; pick the agent (Claude, Antigravity, Codex, or Aider) by the kind of work and check `usage` so you don't exceed the quota; "
    "3) follow along with `list_agents` and `read_output`, and use `send_message` only to course-correct; "
    "4) when they all finish, summarize what each one did and list the agent/* branches for me to review in Ctrl+G. "
    "The agents commit on their own agent/* branches; do NOT merge into the main branch on your own. For now, just confirm you understood and wait for my task."
)

# ---------------------------------------------------------------- events
def log_event(ev):
    ev.setdefault("ts", time.time())
    with open(EVENTS, "a") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    try:                                                         # rotation: the file does not grow forever
        if EVENTS.stat().st_size > 3_000_000:
            data = EVENTS.read_bytes()[-1_000_000:]
            tmp = EVENTS.with_suffix(".tmp"); tmp.write_bytes(data[data.find(b"\n") + 1:]); os.replace(tmp, EVENTS)
    except OSError:
        pass

def read_events(max_age=6 * 3600, limit=4000):
    try:
        with open(EVENTS, "rb") as f:
            f.seek(0, 2); size = f.tell(); f.seek(max(0, size - 1_000_000)); data = f.read()
    except FileNotFoundError:
        return []
    lines = data.decode("utf-8", "ignore").splitlines()
    if size > 1_000_000: lines = lines[1:]                       # the first line may have been cut
    now = time.time(); out = []
    for l in lines[-limit:]:
        try: e = json.loads(l)
        except Exception: continue
        if now - e.get("ts", 0) <= max_age: out.append(e)
    return out

def sessions(project=None):
    """group events into AI sessions with subagents: {sid: {...}}"""
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

# ---------------------------------------------------------------- memory (markdown + FTS index)
def _mdb():
    db = sqlite3.connect(DATA / "memory.db")
    db.execute("create virtual table if not exists mem using fts5(project, kind, tags, text, path unindexed, ts unindexed)")
    return db

def mem_add(project, text, kind="note", tags="", ts=None):
    ts = ts or time.strftime("%Y-%m-%d %H:%M:%S")
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())[:40].strip("-") or "note"
    if project != safe_name(project) and project not in load_projects():
        raise ValueError("invalid project")
    d = MEMDIR / safe_name(project); d.mkdir(parents=True, exist_ok=True)
    kind, tags = re.sub(r"\s+", " ", kind or "note")[:30], re.sub(r"\s+", " ", tags or "")[:100]
    path = d / f"{time.strftime('%Y%m%d-%H%M%S')}-{slug}.md"
    i = 1
    while path.exists():                                         # two notes in the same second do not overwrite each other
        i += 1; path = d / f"{time.strftime('%Y%m%d-%H%M%S')}-{slug}-{i}.md"
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

# ---------------------------------------------------------------- session briefing (what an agent is told when it starts)
BRIEFING_DIR = DATA / "briefing"
MEM_PROTOCOL = (
    "Memory protocol: when you finish a task, or learn something that will still matter next week (a decision and its reason, "
    "the root cause of a bug, a project convention, a gotcha), record ONE short entry with `memory_add` "
    "(kind: decision | bug | convention | note). Do not record trivia, progress chatter or secrets. "
    "Before starting something non-trivial, `memory_search` for what is already known.")
CLI_FALLBACK = ("If the `raidpoint` MCP tools are not available in your harness, use the CLI: "
                "`raidpoint mem search|add|recent <project> ...`, `raidpoint secret list <project>`.")

GIT_PROTOCOL = {
    "commit": ("Git protocol: commit your work as you go, in small logical commits with a clear message, and never end a task "
               "with uncommitted changes. Only commit what you changed (leave files someone else was editing alone). Do not push."),
    "push": ("Git protocol: commit your work as you go, in small logical commits with a clear message, and never end a task with "
             "uncommitted or unpushed work. Only commit what you changed (leave files someone else was editing alone). After "
             "committing, `git push` the branch you are on (`git push -u origin <branch>` the first time); in an agent/* worktree "
             "push that branch and leave the merge to the human or the orchestrator. Never force-push or rewrite pushed history: "
             "if the push is rejected, `git pull --rebase` and push again, and if it still fails say so clearly instead of "
             "leaving the work only on this machine."),
}

def working_rules(git=True, cfg=None):
    """rules every agent gets in its briefing: the git protocol ([agents] git) and the user's own text ([agents] rules)"""
    a = (cfg or load_config()).get("agents") or {}
    out = []
    g = GIT_PROTOCOL.get(str(a.get("git", "push")).strip().lower())
    if g and git: out.append(g)
    extra = str(a.get("rules") or "").strip()
    if extra: out.append(extra)
    return out

def _git_out(d, *a):
    try: return subprocess.run(["git", "-C", d, *a], text=True, capture_output=True, timeout=10).stdout.strip()
    except Exception: return ""

def project_context(project):
    p = load_projects().get(project, {})
    if p.get("host"): return {"remote": True, "host": p["host"], "dir": p.get("dir") or "~"}
    d = pdir(project); ctx = {"dir": d}
    if d and os.path.isdir(d) and git_root(d):
        ctx["branch"] = _git_out(d, "rev-parse", "--abbrev-ref", "HEAD")
        ctx["dirty"] = len([l for l in _git_out(d, "status", "--porcelain").splitlines() if l])
        ctx["commits"] = _git_out(d, "log", "-5", "--format=%h %s").splitlines()
        ctx["origin"] = re.sub(r"//[^@/]+@", "//", _git_out(d, "remote", "get-url", "origin"))     # never leak credentials in a URL
    ctx["docs"] = [f for f in ("README.md", "CLAUDE.md", "AGENTS.md", "CONTRIBUTING.md", "package.json", "pyproject.toml",
                               "Cargo.toml", "go.mod", "Makefile", "docker-compose.yml") if d and os.path.exists(os.path.join(d, f))]
    return ctx

def _tool_lines():
    from . import tools          # imported here: tools imports core
    return "\n".join(f"- `{n}` — {v[0]}" for n, v in tools.TOOLS.items())

def _memory_section(project):
    recent = mem_recent(project, 40)
    keep = [m for m in recent if m["kind"] != "session"][:6]; logs = [m for m in recent if m["kind"] == "session"][:2]
    if not (keep or logs):
        return "No memories recorded yet for this project: you are starting its memory. " + MEM_PROTOCOL
    out = ["Most recent entries (search the rest with `memory_search`):"]
    out += [f"- [{m['kind']}] {m['text'][:240].strip()}  ({m['ts'][:10]})" for m in keep + logs]
    return "\n".join(out) + "\n\n" + MEM_PROTOCOL

def briefing(project, secrets=False):
    """markdown an agent receives when a session starts: where it is, the project context, its tools and the project memory"""
    p = load_projects().get(project, {})
    c = project_context(project)
    where = (f"remote server `{c['host']}`, folder `{c['dir']}`" if c.get("remote") else f"`{c['dir']}`")
    ctx = [f"- Folder: {where}"]
    if p.get("note"):
        ctx.append(f"- Sticky note: {p['note']}")
    if c.get("branch"):
        ctx.append(f"- Branch `{c['branch']}` · {c['dirty']} changed file(s)" + (f" · origin {c['origin']}" if c.get("origin") else ""))
    if not c.get("remote") and c.get("dir") and os.path.isdir(c["dir"]):
        wts = [f"{lbl} ({os.path.basename(wd)})" for lbl, wd in git_targets(c["dir"])[1:]]
        if wts:
            ctx.append("- Active worktrees: " + ", ".join(wts))
    if c.get("commits"): ctx.append("- Last commits: " + "; ".join(c["commits"]))
    if c.get("docs"): ctx.append("- Worth reading first: " + ", ".join(c["docs"]))
    out = [f"# /dev/raid briefing — project '{project}'",
           "You are an AI agent running inside /dev/raid, the operational center for this machine's projects and agents. "
           "The human sees all agents side by side and can read your panes.",
           "", "## Project context", *ctx]
    rules = working_rules(git=bool(c.get("branch") or c.get("remote")))
    if rules: out += ["", "## Working rules", *rules]
    out += [
           "", "## Your tools (MCP server `raidpoint`)", _tool_lines(), CLI_FALLBACK,
           "Use `spawn_agent` with worktree=true for parallel work so agents never edit the same checkout. You only ever see secret "
           "NAMES, never values; `run_with_secrets` injects them into one command after the human approves.",
           "", "## Project memory", _memory_section(project)]
    if secrets:
        names = secret_names(project)
        if names: out += ["", "## Secrets (names only)", ", ".join(names)]
    return "\n".join(out) + "\n"

def write_briefing(project):
    BRIEFING_DIR.mkdir(parents=True, exist_ok=True)
    f = BRIEFING_DIR / f"{safe_name(project)}.md"
    f.write_text(briefing(project, secrets=True))
    return f

def project_resume(project):
    """human-friendly 'where was I?' summary for a tired developer returning to a project"""
    p = load_projects().get(project)
    if not p:
        return f"Project '{project}' not found."
    c = project_context(project)
    lines = [f"# Resume: {project}" + (" ★" if p.get("pinned") else "")]
    if p.get("note"):
        lines.append(f"Note: {p['note']}")
    where = (f"{c['host']}:{c['dir']}" if c.get("remote") else c.get("dir", ""))
    lines.append(f"Folder: {where}")
    if c.get("branch"):
        lines.append(f"Branch: {c['branch']} ({c['dirty']} uncommitted change(s))")
    if not c.get("remote") and c.get("dir") and os.path.isdir(c["dir"]):
        changes = git_changes(c["dir"]) or []
        if changes:
            lines.append("Changed files: " + ", ".join(f"{st} {path}" for st, path in changes[:10])
                         + (f" (+{len(changes) - 10} more)" if len(changes) > 10 else ""))
        wts = git_targets(c["dir"])[1:]
        if wts:
            wt_info = []
            for lbl, wd in wts:
                wc = len(git_changes(wd) or [])
                wt_info.append(f"{lbl} ({wc} dirty)" if wc else lbl)
            lines.append("Open worktrees: " + ", ".join(wt_info))
    if c.get("commits"):
        lines.append("Recent commits:\n  " + "\n  ".join(c["commits"]))
    panes = list_panes(project)
    if panes:
        lines.append("Open panes: " + ", ".join(f"{x['title']} ({x['cmd']})" for x in panes))
    S = sessions(project)
    if S:
        lines.append("AI sessions: " + ", ".join(f"{s['harness']}:{s['status']} ({ago(s['last'])} ago)" for s in S.values()))
    recent = mem_recent(project, 20)
    keep = [m for m in recent if m["kind"] != "session"][:5]
    logs = [m for m in recent if m["kind"] == "session"][:2]
    if keep or logs:
        lines.append("Memory:")
        for m in keep + logs:
            lines.append(f"  [{m['kind']}] ({m['ts'][:10]}) {m['text'][:200].strip()}")
    else:
        lines.append("Memory: (none yet)")
    return "\n".join(lines) + "\n"

def mem_session_log(project, session_id, evs=None):
    """automatic project log: when a session ends, record what was asked and what changed (no LLM, only facts).
    Without this the memory stays empty, because agents rarely call memory_add on their own."""
    if not (project and session_id) or project not in load_projects(): return None          # never log for a removed project
    if evs is None: evs = [e for e in read_events(max_age=3 * 86400, limit=20000) if e.get("session_id") == session_id]
    prompts = [e["prompt"] for e in evs if e.get("event") == "UserPromptSubmit" and e.get("prompt")]
    if not prompts: return None
    tag = session_id[:8]
    if any(tag in (m["tags"] or "") for m in mem_recent(project, 200)): return None         # already logged
    start, end = min(e["ts"] for e in evs), max(e["ts"] for e in evs)
    d = pdir(project) if not load_projects().get(project, {}).get("host") else None
    text = (f"Session {time.strftime('%Y-%m-%d', time.localtime(start))} ({dur_short(int(end - start))}, "
            f"{len(prompts)} prompt(s)). First request: \"{prompts[0].strip()}\".")
    if d and os.path.isdir(d) and git_root(d):
        since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start)); until = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end + 60))
        commits = [l for l in _git_out(d, "log", f"--since={since}", f"--until={until}", "--format=%s", "-8").splitlines() if l]
        if commits: text += " Commits: " + "; ".join(commits) + "."
        if time.time() - end < 3600:                  # "working tree after" only makes sense for a session that just ended
            dirty = len([l for l in _git_out(d, "status", "--porcelain").splitlines() if l])
            if dirty: text += f" Working tree after: {dirty} changed file(s)."
    return mem_add(project, text, kind="session", tags=f"auto,{tag}", ts=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end)))

def mem_backfill(idle_s=1800):
    """turn the sessions already recorded in the event log into memory entries (skips live ones). Returns {project: n}"""
    by = {}
    for e in read_events(max_age=30 * 86400, limit=200000):
        if e.get("session_id") and e.get("project"): by.setdefault((e["project"], e["session_id"]), []).append(e)
    done = {}
    for (proj, sid), es in sorted(by.items(), key=lambda kv: min(x["ts"] for x in kv[1])):
        if time.time() - max(x["ts"] for x in es) < idle_s: continue
        try:
            if mem_session_log(proj, sid, es): done[proj] = done.get(proj, 0) + 1
        except Exception: pass
    return done

AGENTS_BEGIN, AGENTS_END = "<!-- devraid:begin -->", "<!-- devraid:end -->"

def agents_md_block():
    return "\n".join([AGENTS_BEGIN, "## /dev/raid", "",
        "This project runs inside /dev/raid. Agents opened there get a briefing (project context, tools, memory) automatically; "
        "agents opened elsewhere should follow this.", "",
        "### Tools (MCP server `raidpoint`)", _tool_lines(), "", CLI_FALLBACK, "",
        "### Memory", "Start with `memory_recent` to see what is known. " + MEM_PROTOCOL, "",
        *[x for r in working_rules() for x in (r, "")],
        "Secrets: you only see NAMES (`secret_names`); never ask for or print a value. Parallel agents: `spawn_agent` with worktree=true.",
        AGENTS_END, ""])

def write_agents_md(project, remove=False):
    """add/refresh (or remove) the managed block in <project>/AGENTS.md; returns (path, error). Opt-in: it edits the repo."""
    p = load_projects().get(project, {})
    if p.get("host"): return None, "remote projects have no local folder"
    d = pdir(project)
    if not d or not os.path.isdir(d): return None, "project folder not found"
    f = Path(d) / "AGENTS.md"; cur = f.read_text() if f.exists() else ""
    pat = re.compile(re.escape(AGENTS_BEGIN) + r".*?" + re.escape(AGENTS_END) + r"\n?", re.S)
    if remove:
        new = pat.sub("", cur).rstrip("\n"); new = new + "\n" if new.strip() else ""
    elif pat.search(cur): new = pat.sub(lambda m: agents_md_block(), cur)
    else: new = (cur.rstrip("\n") + "\n\n" if cur.strip() else "") + agents_md_block()
    if remove and not new: f.unlink(missing_ok=True)
    else: f.write_text(new)
    return str(f), None

# ---------------------------------------------------------------- secrets (system keyring)
def _st(*a, inp=None):
    return subprocess.run(["secret-tool", *a], text=True, capture_output=True, input=inp)

SECRETS_REV = DATA / "secrets-rev.json"        # {project: counter}: bumped whenever a secret is added or removed
SECRETS_SEEN = DATA / "secrets-seen.json"      # {session_id: {project: {"rev", "names"}}}: what each AI session was told

def _json_file(path):
    try:
        d = json.loads(path.read_text())
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}

def _bump_rev(project):
    d = _json_file(SECRETS_REV); d[project] = int(d.get(project, 0)) + 1
    write_json_atomic(SECRETS_REV, d)

SECRETS_DIR = HOME / "secrets"                 # file backend: one 0600 JSON per project ({name: value})

def secrets_backend():
    """'keyring' (Secret Service, the default) or 'file' (servers without a keyring): RAIDPOINT_SECRETS or [secrets] backend"""
    b = os.environ.get("RAIDPOINT_SECRETS") or (load_config().get("secrets") or {}).get("backend") or "keyring"
    return "file" if str(b).strip().lower() == "file" else "keyring"

def _sfile(project):
    from urllib.parse import quote
    return SECRETS_DIR / (quote(project, safe="") + ".json")

def _sread(project):
    return {k: v for k, v in _json_file(_sfile(project)).items() if isinstance(v, str)}

def _swrite(project, d):
    SECRETS_DIR.mkdir(parents=True, exist_ok=True); os.chmod(SECRETS_DIR, 0o700)
    f = _sfile(project)
    if not d: f.unlink(missing_ok=True); return
    tmp = str(f) + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)      # never readable by others, not even for an instant
    with os.fdopen(fd, "w") as fh: json.dump(d, fh, ensure_ascii=False)
    os.chmod(tmp, 0o600); os.replace(tmp, f)

def secret_set(project, name, value):
    if secrets_backend() == "file":
        if not (project and name): return False
        d = _sread(project); d[name] = value; _swrite(project, d); _bump_rev(project); return True
    r = _st("store", "--label", f"raidpoint:{project}:{name}", "service", "raidpoint", "project", project, "name", name, inp=value)
    if r.returncode == 0: _bump_rev(project)
    return r.returncode == 0

def secret_get(project, name):
    if secrets_backend() == "file": return _sread(project).get(name) or None
    r = _st("lookup", "service", "raidpoint", "project", project, "name", name)
    return r.stdout if r.returncode == 0 and r.stdout else None

def secret_rm(project, name):
    if secrets_backend() == "file":
        d = _sread(project)
        if name not in d: return False
        del d[name]; _swrite(project, d); _bump_rev(project); return True
    ok = _st("clear", "service", "raidpoint", "project", project, "name", name).returncode == 0
    if ok: _bump_rev(project)
    return ok

def secret_names(project):
    if secrets_backend() == "file": return sorted(_sread(project))
    r = _st("search", "--all", "service", "raidpoint", "project", project)
    return sorted(set(re.findall(r"attribute\.name = (.+)", r.stdout + r.stderr)))

SECRET_HOWTO = ("You only ever see secret NAMES, never values. To use one, call the MCP tool raidpoint.run_with_secrets "
                "(command, secrets=[NAMES], purpose): the human approves each use, the value is injected only into that "
                "command's environment and is masked in its output. Never ask the user to paste a secret into the chat; "
                "if one is missing, ask them to add it in Project secrets (the lock button in the /dev/raid title bar).")

def secret_announcement(session_id, project, event):
    """Context text for an AI session about the project's secrets (NAMES only). SessionStart: the full list and how to use
    it. Later prompts: only what was added/removed since this session was last told (nothing when nothing changed)."""
    if not (session_id and project): return ""
    rev = int(_json_file(SECRETS_REV).get(project, 0))
    seen = _json_file(SECRETS_SEEN)
    rec = (seen.get(session_id) or {}).get(project)
    if event != "SessionStart" and rec and rec.get("rev") == rev: return ""
    names = secret_names(project)
    prev = set(rec.get("names", [])) if rec else None
    seen.setdefault(session_id, {})[project] = {"rev": rev, "names": names}
    for k in list(seen)[:-200]: del seen[k]                      # keep the most recent sessions only
    write_json_atomic(SECRETS_SEEN, seen)
    if event == "SessionStart" or prev is None:
        return (f"# Secrets of project '{project}' (/dev/raid)\nAvailable by name: {', '.join(names)}.\n{SECRET_HOWTO}\n") if names else ""
    added, removed = [n for n in names if n not in prev], sorted(prev - set(names))
    if not added and not removed: return ""
    out = f"# Secrets of project '{project}' changed (/dev/raid)\n"
    if added: out += f"Added: {', '.join(added)}.\n"
    if removed: out += f"Removed: {', '.join(removed)}.\n"
    return out + (f"{SECRET_HOWTO}\n" if added else "")

def redact(text, values):
    for v in sorted(values, key=len, reverse=True):
        if v and len(v) >= 4:
            text = text.replace(v, "«secret»")
            text = text.replace(shlex.quote(v), "«secret»")
    return text

def pending_requests(max_age=130):
    """approval requests still waiting for the human (oldest first)"""
    out = []
    for f in REQDIR.glob("*.json"):
        try: r = json.loads(f.read_text())
        except Exception: continue
        if isinstance(r, dict) and r.get("status") == "pending" and time.time() - r.get("ts", 0) <= max_age: out.append(r)
    return sorted(out, key=lambda r: r.get("ts", 0))

def answer_request(rid, ok):
    """approve/deny a pending request by id (or a unique prefix of it). Returns the request, or None if there is no such one"""
    hit = [r for r in pending_requests() if str(r.get("id", "")).startswith(rid)] if re.fullmatch(r"[0-9a-f]{1,10}", rid or "") else []
    if len(hit) != 1: return None
    r = hit[0]; f = REQDIR / f"{r['id']}.json"
    try:
        if json.loads(f.read_text()).get("status") != "pending": return None       # someone (the app) answered first
        r["status"] = "approved" if ok else "denied"; f.write_text(json.dumps(r))
    except Exception: return None
    return r

def ask_approval(kind, project, detail, timeout=120):
    """ask the human for approval: a dialog in the /dev/raid app, or `raidpoint approvals` on a machine without the app.
    Nobody answering = denied."""
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
    """run a command with secrets injected as environment variables; output has secrets masked"""
    if load_projects().get(project, {}).get("host"):
        return {"error": "run_with_secrets only works on local projects"}
    have = secret_names(project)
    missing = [n for n in names if n not in have]
    if missing: return {"error": f"unknown secrets: {missing}"}
    detail = f"Command: {command[:1500]}{'…' if len(command) > 1500 else ''}\nSecrets: {', '.join(names)}\nPurpose: {purpose or '(not given)'}"
    if not ask_approval("secret", project, detail):
        return {"error": "denied by the user (or no answer within 120s)"}
    env = dict(os.environ); vals = []
    for n in names:
        v = secret_get(project, n); env[n] = v or ""; vals.append(v or "")
    try:
        r = subprocess.run(command, shell=True, cwd=pdir(project), env=env, text=True,
                           capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        return {"error": "timeout (300s)"}
    return {"exit": r.returncode, "stdout": redact(r.stdout, vals)[-20000:], "stderr": redact(r.stderr, vals)[-8000:]}


# ---------------------------------------------------------------- GitHub repositories (via gh)
def gh_ok():
    return bool(shutil.which("gh")) and subprocess.run(["gh", "auth", "status"], capture_output=True).returncode == 0

def gh_repos(force=False, ttl=300):
    """all repositories of the user and their orgs (5 min cache), most recent first"""
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

NWO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

def check_nwo(nwo):
    if not NWO_RE.match(nwo or "") or any(part in (".", "..") for part in nwo.split("/")):
        raise ValueError(f"invalid repository: {nwo!r} (use owner/repo)")

def workspace_path(nwo):
    """~/.raid_point/workspaces/<repo> (if another repo with that name already exists: <owner>-<repo>)"""
    check_nwo(nwo)
    owner, name = nwo.split("/", 1)
    p = WS / name
    if p.exists():
        r = subprocess.run(["git", "-C", str(p), "remote", "get-url", "origin"], text=True, capture_output=True)
        if nwo.lower() not in r.stdout.lower(): p = WS / f"{owner}-{name}"
    return p

def ensure_workspace(nwo):
    """clone the repo into the workspace if it isn't there yet; returns (path, error)"""
    p = workspace_path(nwo)
    if (p / ".git").exists(): return str(p), None
    try: r = subprocess.run(["gh", "repo", "clone", nwo, str(p)], text=True, capture_output=True, timeout=900)
    except subprocess.TimeoutExpired: return None, "the clone took longer than 15 minutes and was cancelled"
    return (str(p), None) if r.returncode == 0 else (None, (r.stderr or r.stdout).strip()[-400:])


# ---------------------------------------------------------------- token usage (Claude Code, via transcripts)
CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
USAGE_STATE = CM / "usage.json"
BUCKET = 300  # seconds

def usage_update(max_age_days=8):
    """read Claude Code transcripts (incrementally) and accumulate tokens per 5-min bucket/project/model.
    Deduplicates by message.id (one response shows up on several transcript lines)."""
    from datetime import datetime
    try: st = json.loads(USAGE_STATE.read_text())
    except Exception: st = {}
    files, seen, buckets = st.get("files", {}), st.get("seen", {}), st.get("buckets", {})
    now = time.time(); cutoff = now - max_age_days * 86400
    changed = False; proj_cache = {}
    for path in CLAUDE_PROJECTS.rglob("*.jsonl"):
        try: s = path.stat()
        except OSError: continue
        if s.st_mtime < cutoff: continue
        off = files.get(str(path), 0)
        if s.st_size < off: off = 0
        if s.st_size == off: continue
        with open(path, "rb") as fh:
            fh.seek(off); data = fh.read()
        end = data.rfind(b"\n") + 1
        files[str(path)] = off + end; changed = True
        for line in data[:end].split(b"\n"):
            if b'"usage"' not in line: continue
            try: o = json.loads(line)
            except Exception: continue
            m = o.get("message") or {}; u = m.get("usage")
            if not u: continue
            mid = m.get("id") or o.get("requestId") or o.get("uuid")
            if mid in seen: continue
            try: ts = datetime.fromisoformat(o["timestamp"].replace("Z", "+00:00")).timestamp()
            except Exception: continue
            if ts < cutoff: continue
            seen[mid] = ts
            cwd = o.get("cwd") or ""
            if cwd not in proj_cache:
                proj_cache[cwd] = project_for_cwd(cwd) or (os.path.basename(cwd.rstrip("/")) if cwd else "?")
            proj = proj_cache[cwd]
            key = f"{int(ts // BUCKET)}|{proj}|{m.get('model') or '?'}"
            b = buckets.setdefault(key, [0, 0, 0, 0, 0])
            b[0] += u.get("input_tokens", 0); b[1] += u.get("output_tokens", 0)
            b[2] += u.get("cache_creation_input_tokens", 0); b[3] += u.get("cache_read_input_tokens", 0); b[4] += 1
    seen = {k: v for k, v in seen.items() if v >= cutoff}
    buckets = {k: v for k, v in buckets.items() if int(k.split("|")[0]) * BUCKET >= cutoff}
    if changed:
        write_json_atomic(USAGE_STATE, {"files": files, "seen": seen, "buckets": buckets})
    return buckets

def usage_summary(buckets=None):
    """totals per window (5h, 24h, 7d), per project and per model. 'new' = input + output + cache creation."""
    buckets = buckets if buckets is not None else usage_update()
    now = time.time()
    wins = {"5h": 5 * 3600, "24h": 24 * 3600, "7d": 7 * 86400}
    out = {w: {"inp": 0, "out": 0, "cache_create": 0, "cache_read": 0, "msgs": 0, "by_project": {}, "by_model": {}} for w in wins}
    for key, v in buckets.items():
        t, proj, model = key.split("|", 2); t = int(t) * BUCKET
        for w, secs in wins.items():
            if now - t <= secs:
                o = out[w]
                o["inp"] += v[0]; o["out"] += v[1]; o["cache_create"] += v[2]; o["cache_read"] += v[3]; o["msgs"] += v[4]
                new = v[0] + v[1] + v[2]
                o["by_project"][proj] = o["by_project"].get(proj, 0) + new
                o["by_model"][model] = o["by_model"].get(model, 0) + new
    for o in out.values():
        o["new"] = o["inp"] + o["out"] + o["cache_create"]
    return out

def fmt_tokens(n):
    return f"{n/1e6:.1f}M" if n >= 1e6 else (f"{n/1e3:.0f}k" if n >= 1e3 else str(n))


# ---------------------------------------------------------------- plan limits (from the Claude Code statusLine)
PLAN_FILE = DATA / "plan.json"

def plan_status():
    """latest 5h/7d percentages written by `raidpoint statusline`; expired windows are dropped"""
    try: d = json.loads(PLAN_FILE.read_text())
    except Exception: return None
    now = time.time()
    for k in ("five_hour", "seven_day"):
        w = d.get(k)
        if w and w.get("resets_at") and w["resets_at"] < now: d[k] = None
    d["age_s"] = now - d.get("ts", 0)
    return d


_CODEX = {"key": None, "val": None}

def codex_plan(max_files=12):
    """Codex plan limits (5h / week), credits and plan type, read from the latest `token_count`
    with `rate_limits` in the ~/.codex/sessions logs (Codex writes this on its own). None if there is no data."""
    from datetime import datetime
    root = Path.home() / ".codex" / "sessions"
    try:
        files = sorted(root.glob("**/rollout-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:max_files]
    except OSError:
        return None
    if not files: return None
    key = (str(files[0]), files[0].stat().st_mtime)
    if _CODEX["key"] != key:
        found = None
        for f in files:
            try:
                with open(f, "rb") as fh:
                    fh.seek(0, 2); size = fh.tell(); fh.seek(max(0, size - 600_000)); data = fh.read()
            except OSError:
                continue
            for line in reversed(data.decode("utf-8", "ignore").splitlines()):
                if '"rate_limits"' not in line or '"token_count"' not in line: continue
                try: e = json.loads(line)
                except Exception: continue
                rl = (e.get("payload") or {}).get("rate_limits")
                if not rl: continue
                try: ts = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")).timestamp()
                except Exception: ts = f.stat().st_mtime
                found = {"plan_type": rl.get("plan_type"), "primary": rl.get("primary"), "secondary": rl.get("secondary"),
                         "credits": rl.get("credits") or {}, "ts": ts, "reached": rl.get("rate_limit_reached_type")}
                break
            if found: break
        _CODEX["key"], _CODEX["val"] = key, found
    d = _CODEX["val"]
    if not d: return None
    d = dict(d); now = time.time()
    for k in ("primary", "secondary"):                       # window that already reset = stale data
        w = d.get(k)
        if w and w.get("resets_at") and w["resets_at"] < now: d[k] = None
    d["age_s"] = now - d["ts"]
    return d

# ---------------------------------------------------------------- git: recent commits and CI (GitHub Actions)
_GD = {}

def ci_state(runs):
    if not runs: return "none"
    r = runs[0]
    if r["status"] != "completed": return "running"
    return {"success": "ok", "failure": "fail", "timed_out": "fail", "startup_failure": "fail"}.get(r["conclusion"], "other")

def git_detail(d, ncommits=6, nruns=6):
    """branch, recent commits and recent GitHub Actions runs of the current branch"""
    from datetime import datetime
    r = subprocess.run(["git", "-C", d, "symbolic-ref", "--short", "HEAD"], text=True, capture_output=True)
    if r.returncode != 0:
        r = subprocess.run(["git", "-C", d, "rev-parse", "--abbrev-ref", "HEAD"], text=True, capture_output=True)
    if r.returncode != 0: return None
    out = {"branch": r.stdout.strip(), "commits": [], "runs": [], "ci": "none"}
    r = subprocess.run(["git", "-C", d, "log", "-n", str(ncommits), "--pretty=format:%h%x09%s%x09%an%x09%ct"],
                       text=True, capture_output=True)
    for l in r.stdout.splitlines():
        f = l.split("\t")
        if len(f) == 4: out["commits"].append({"sha": f[0], "msg": f[1], "author": f[2], "ts": int(f[3])})
    if shutil.which("gh") and out["branch"] != "HEAD":
        try:
            g = subprocess.run(["gh", "run", "list", "--branch", out["branch"], "--limit", str(nruns), "--json",
                                "databaseId,name,displayTitle,status,conclusion,event,createdAt,url"],
                               cwd=d, text=True, capture_output=True, timeout=15)
            for x in (json.loads(g.stdout or "[]") if g.returncode == 0 else []):
                try: ts = datetime.fromisoformat(x["createdAt"].replace("Z", "+00:00")).timestamp()
                except Exception: ts = 0
                out["runs"].append({"id": x["databaseId"], "name": x["name"], "title": x["displayTitle"],
                                    "status": x["status"], "conclusion": x.get("conclusion"),
                                    "event": x["event"], "ts": ts, "url": x["url"]})
        except Exception:
            pass
    out["ci"] = ci_state(out["runs"])
    return out

def _git(d, *a, timeout=30):
    return subprocess.run(["git", "-C", d, *a], text=True, capture_output=True, timeout=timeout)

def git_targets(d):
    """git folders of the project: the main one + agent worktrees -> [(label, path)]"""
    r = _git(d, "worktree", "list", "--porcelain")
    if r.returncode != 0: return []
    paths = [l[9:] for l in r.stdout.splitlines() if l.startswith("worktree ")]
    out = []
    for i, p in enumerate(paths):
        out.append(("main" if i == 0 else os.path.basename(p), p))
    return out

def git_changes(d):
    """changed files -> [(status, path)]; status: M modified, A added (staged), D deleted, ? new, R renamed"""
    r = _git(d, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if r.returncode != 0: return None
    out, parts, i = [], r.stdout.split("\0"), 0
    while i < len(parts):
        e = parts[i]; i += 1
        if len(e) < 4: continue
        xy, path = e[:2], e[3:]
        if "R" in xy or "C" in xy: i += 1          # next field is the source path
        st = "?" if xy == "??" else ("D" if "D" in xy else ("A" if "A" in xy else ("R" if "R" in xy else "M")))
        out.append((st, path))
    return out

def git_diff(d, path, status):
    """diff of one file (includes what is already staged); new files: shows the whole content as added"""
    if status == "?":
        r = _git(d, "diff", "--no-index", "--", os.devnull, path)    # exits with 1 when there are differences
    else:
        r = _git(d, "diff", "HEAD", "--", path)
        if r.returncode != 0 or not r.stdout:                         # repo without commits
            r = _git(d, "diff", "--cached", "--", path)
    txt = r.stdout
    return txt if len(txt) < 400_000 else txt[:400_000] + "\n… (diff truncated)"

def git_revert(d, path, status):
    """discard the changes of ONE file; returns an error message or None"""
    if status == "?":
        f = Path(d, path)
        try: f.unlink()
        except OSError as e: return str(e)
        return None
    r = _git(d, "restore", "--source=HEAD", "--staged", "--worktree", "--", path)
    return None if r.returncode == 0 else (r.stderr.strip() or "failed")

def git_commit(d, msg, paths=None):
    """commit the chosen files (or everything); returns (ok, output)"""
    if not msg.strip(): return False, "empty message"
    r = _git(d, "add", "-A", "--", *(paths or ["."]))
    if r.returncode != 0: return False, r.stderr.strip()
    r = _git(d, "commit", "-m", msg, "--", *(paths or []) ) if paths else _git(d, "commit", "-m", msg)
    return r.returncode == 0, (r.stdout + r.stderr).strip()

_IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "target", "dist", "build", ".mypy_cache", ".pytest_cache"}

def project_files(d, limit=3000):
    """tracked + untracked (non-ignored) relative file paths in folder d"""
    if not d or not os.path.isdir(d): return []
    r = _git(d, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    if r.returncode == 0:
        out = [p for p in r.stdout.split("\0") if p and os.path.isfile(os.path.join(d, p))]
        return sorted(set(out))[:limit]
    out = []
    for root, dirs, files in os.walk(d):
        dirs[:] = [x for x in sorted(dirs) if x not in _IGNORE_DIRS and not x.startswith(".")]
        for f in sorted(files):
            rel = os.path.relpath(os.path.join(root, f), d)
            out.append(rel)
            if len(out) >= limit: return out
    return out

def git_line_diff(d, path):
    """1-based line markers vs HEAD: {line_no: 'add' | 'mod' | 'del'}"""
    if not d or not path: return {}
    r = _git(d, "diff", "-U0", "HEAD", "--", path)
    if r.returncode != 0: return {}
    marks = {}
    for ln in r.stdout.splitlines():
        if not ln.startswith("@@"): continue
        m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", ln)
        if not m: continue
        old_cnt = int(m.group(2)) if m.group(2) is not None else 1
        new_start = int(m.group(3))
        new_cnt = int(m.group(4)) if m.group(4) is not None else 1
        if new_cnt == 0 and old_cnt > 0:
            marks[max(1, new_start)] = "del"
        else:
            kind = "mod" if old_cnt > 0 else "add"
            for i in range(new_start, new_start + new_cnt):
                marks[i] = kind
    return marks

def git_first_changed_line(d, path):
    """first 1-based line changed in `path` vs HEAD (1 if none or untracked)"""
    marks = git_line_diff(d, path)
    return min(marks) if marks else 1

def git_merge_worktree(main_dir, wt_dir):
    """merge an agent worktree branch into main_dir (--no-ff); returns (ok, message)"""
    if os.path.realpath(main_dir) == os.path.realpath(wt_dir):
        return False, "already on main"
    br = _git(wt_dir, "symbolic-ref", "--short", "HEAD").stdout.strip()
    if not br: return False, "worktree has no branch (detached HEAD)"
    if git_changes(wt_dir):
        return False, f"worktree '{br}' has uncommitted changes; commit or revert them first"
    r = _git(main_dir, "merge", "--no-edit", br)
    return r.returncode == 0, (r.stdout + "\n" + r.stderr).strip()

def git_remove_worktree(main_dir, wt_dir, force=False):
    """remove an agent worktree and delete its branch if merged (or if force); returns (ok, message)"""
    if os.path.realpath(main_dir) == os.path.realpath(wt_dir):
        return False, "cannot remove the main checkout"
    br = _git(wt_dir, "symbolic-ref", "--short", "HEAD").stdout.strip()
    args = ["worktree", "remove"] + (["--force"] if force else []) + [wt_dir]
    r = _git(main_dir, *args)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip()
    if br and br.startswith("agent/"):
        _git(main_dir, "branch", "-D" if force else "-d", br)
    return True, f"removed {os.path.basename(wt_dir)}"

def git_detail_cached(d, ttl=60):
    ts, v = _GD.get(d, (0, None))
    if time.time() - ts > ttl:
        try: v = git_detail(d)
        except Exception: pass
        _GD[d] = (time.time(), v)
    return v

def ago(ts):
    s = max(0, int(time.time() - ts))
    return f"{s}s" if s < 60 else (f"{s // 60}min" if s < 3600 else (f"{s // 3600}h" if s < 86400 else f"{s // 86400}d"))


# ---------------------------------------------------------------- auto-update
VERSION = "0.2.0"
REPO = "kleber-code/dev-raid"
APP_ROOT = Path(__file__).resolve().parent.parent      # checkout (dev) or PREFIX/lib/devraid (installed)
UPDATE_STATE = DATA / "update.json"
UPDATE_EVERY = 6 * 3600

def _ver(t):
    return tuple(int(x) for x in re.findall(r"\d+", t)[:3])

def install_mode():
    """'git' (running from a checkout), 'package' (distro package: the package manager updates it) or 'release'"""
    if (APP_ROOT / ".git").exists(): return "git"
    if str(APP_ROOT).startswith("/usr/") and not str(APP_ROOT).startswith("/usr/local/"): return "package"
    return "release"

def _app_git(*a, timeout=60):
    return subprocess.run(["git", "-C", str(APP_ROOT), *a], text=True, capture_output=True, timeout=timeout)

COMMIT_FILE = APP_ROOT / "COMMIT"      # written by install.sh/make: the GitHub commit this install was built from
BRANCH = "main"

def installed_commit():
    """hash of the installed code: HEAD of the checkout, or the COMMIT file (None if unknown, e.g. a copied/dirty tree)"""
    if (APP_ROOT / ".git").exists():
        h = _app_git("rev-parse", "HEAD").stdout.strip()
        return h or None
    try: return COMMIT_FILE.read_text().strip() or None
    except Exception: return None

def _gh_api(path, accept="application/vnd.github+json"):
    import urllib.request
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/{path}",
                                 headers={"User-Agent": "devraid-updater", "Accept": accept})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode()

def _res(status, msg, frm=None, to=None, count=None, subject=None):
    return {"status": status, "msg": msg, "version": subject or to, "from": frm, "to": to, "count": count, "subject": subject}

def check_update(apply=False):
    """Compares the installed commit with GitHub's main (a different hash that is AHEAD of yours = update).
    By default it only CHECKS; apply=True installs. Returns {"status": "updated"|"available"|"current"|"skipped"|"error", "msg", "from", "to", "count", "subject"}."""
    mode = install_mode()
    try:
        if mode == "package":
            return _res("skipped", "installed by the system package manager; update it there")
        if mode == "git":
            if _app_git("fetch", "--quiet").returncode != 0:
                return _res("error", "git fetch failed")
            if not _app_git("rev-parse", "--abbrev-ref", "@{u}").stdout.strip():
                return _res("skipped", "current branch has no upstream")
            frm = _app_git("rev-parse", "--short", "HEAD").stdout.strip()
            behind = int(_app_git("rev-list", "--count", "HEAD..@{u}").stdout.strip() or 0)
            if not behind:
                return _res("current", "already up to date", frm, frm)
            to = _app_git("rev-parse", "--short", "@{u}").stdout.strip()
            subj = _app_git("log", "-1", "--format=%s", "@{u}").stdout.strip()
            if not apply:
                return _res("available", f"{behind} new commit(s): {subj}", frm, to, behind, subj)
            if _app_git("status", "--porcelain", "--untracked-files=no").stdout.strip():
                return _res("skipped", "local changes in the checkout; not pulling", frm, to, behind, subj)
            if _app_git("pull", "--ff-only", "--quiet").returncode != 0:
                return _res("skipped", "branch diverged from upstream; not pulling", frm, to, behind, subj)
            return _res("updated", f"pulled {behind} commit(s): {subj}", frm, to, behind, subj)
        # installed copy (install.sh): hash-based, straight from GitHub main
        cur = installed_commit()
        if not cur:
            return _res("skipped", "unknown installed version (copied tree): run install.sh once to enable update tracking")
        head = _gh_api(f"commits/{BRANCH}", "application/vnd.github.sha").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", head):
            return _res("error", "unexpected answer from GitHub")
        if head == cur:
            return _res("current", "already up to date", cur[:7], head[:7])
        count = subj = None
        try:
            cmp = json.loads(_gh_api(f"compare/{cur}...{head}"))
            if cmp.get("status") in ("behind", "identical"):       # you are ahead of main (dev build): nothing to install
                return _res("current", "this install is not behind main", cur[:7], head[:7])
            count = cmp.get("ahead_by"); cs = cmp.get("commits") or []
            if cs: subj = (cs[-1]["commit"]["message"] or "").splitlines()[0]
        except Exception:
            pass                                                   # unknown base commit: still offer the update
        if not subj:
            subj = (json.loads(_gh_api(f"commits/{head}"))["commit"]["message"] or "").splitlines()[0]
        if not apply:
            return _res("available", f"{count or 'new'} change(s): {subj}", cur[:7], head[:7], count, subj)
        prefix = APP_ROOT.parent.parent                 # PREFIX/lib/devraid -> PREFIX
        import tempfile, urllib.request
        with tempfile.TemporaryDirectory() as td:
            sh = Path(td) / "install.sh"
            urllib.request.urlretrieve(f"https://raw.githubusercontent.com/{REPO}/{head}/install.sh", sh)
            env = dict(os.environ, DEVRAID_REF=head, DEVRAID_PREFIX=str(prefix), DEVRAID_YES="1", DEVRAID_NO_RESTART="1")
            if not (APP_ROOT / "bin" / "devraid-gui").exists(): env["DEVRAID_HEADLESS"] = "1"     # a server install stays one
            r = subprocess.run(["sh", str(sh)], env=env, stdin=subprocess.DEVNULL, text=True,
                               capture_output=True, timeout=600)
        if r.returncode != 0:
            return _res("error", (r.stderr or r.stdout).strip()[-300:], cur[:7], head[:7], count, subj)
        return _res("updated", f"updated to {head[:7]}: {subj}", cur[:7], head[:7], count, subj)
    except Exception as e:
        return _res("error", str(e)[:300])

def update_check_due():
    """result of a CHECK (never installs) unless auto-check is off or the user chose to skip that exact version"""
    if not load_config().get("updates", {}).get("auto", True):
        return None
    res = check_update(apply=False)
    try: st = json.loads(UPDATE_STATE.read_text())
    except Exception: st = {}
    try: write_json_atomic(UPDATE_STATE, {**st, "last": time.time(), "status": res["status"], "to": res.get("to")})
    except Exception: pass
    if res["status"] == "available" and res.get("to") and res["to"] == st.get("skip"):
        return None
    return res

def skip_update(to):
    try: st = json.loads(UPDATE_STATE.read_text())
    except Exception: st = {}
    try: write_json_atomic(UPDATE_STATE, {**st, "skip": to})
    except Exception: pass
