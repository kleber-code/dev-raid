"""Núcleo compartilhado do /dev/raid: projetos, eventos, memória, segredos, tmux (local/remoto)."""
import fcntl, json, os, re, shlex, shutil, sqlite3, subprocess, time, uuid
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
SOCKET = os.environ.get("RAIDPOINT_SOCKET", "tp")   # nome do socket do tmux (servidor próprio, separado do seu tmux)
TMUX = ["tmux", "-L", SOCKET, "-f", str(CFG / "tmux.conf")]

# ---------------------------------------------------------------- projetos
PROJ = CFG / "projects.json"

CONFIG_DEFAULT = {
    "terminal": {"font": "Noto Sans Mono 11", "zoom_step": 0.1, "theme": "Catppuccin Mocha",
                 "accent": "Padrão do tema", "cursor": "Bloco", "cursor_blink": False},
    "window": {"sidebar_width": 190},
    # formato GTK: "<Control>d", "<Control><Shift>p"…  ("" desativa)
    "keys": {
        "palette": "<Control>d", "settings": "<Control>comma", "changes": "<Control>g",
        "agents_panel": "<Control>j", "sidebar": "<Control>b",
        "zoom_in": "<Control>plus", "zoom_out": "<Control>minus", "zoom_reset": "<Control>0",
        "copy": "<Control><Shift>c", "paste": "<Control><Shift>v",
    },
}

THEMES = {   # fundo, texto, 16 cores
    "Catppuccin Mocha": ("#1e1e2e", "#cdd6f4", "#45475a #f38ba8 #a6e3a1 #f9e2af #89b4fa #f5c2e7 #94e2d5 #bac2de "
                                                "#585b70 #f38ba8 #a6e3a1 #f9e2af #89b4fa #f5c2e7 #94e2d5 #a6adc8"),
    "Tokyo Night": ("#1a1b26", "#c0caf5", "#15161e #f7768e #9ece6a #e0af68 #7aa2f7 #bb9af7 #7dcfff #a9b1d6 "
                                          "#414868 #f7768e #9ece6a #e0af68 #7aa2f7 #bb9af7 #7dcfff #c0caf5"),
    "Gruvbox Dark": ("#282828", "#ebdbb2", "#282828 #cc241d #98971a #d79921 #458588 #b16286 #689d6a #a89984 "
                                           "#928374 #fb4934 #b8bb26 #fabd2f #83a598 #d3869b #8ec07c #ebdbb2"),
    "Nord": ("#2e3440", "#d8dee9", "#3b4252 #bf616a #a3be8c #ebcb8b #81a1c1 #b48ead #88c0d0 #e5e9f0 "
                                   "#4c566a #bf616a #a3be8c #ebcb8b #81a1c1 #b48ead #8fbcbb #eceff4"),
}

# cores da INTERFACE por tema (o terminal usa THEMES). Chaves: fundo, painel, borda-escura, linhas, cinza, texto, destaque, ...
THEME_UI = {
    "Catppuccin Mocha": dict(bg="#1e1e2e", mantle="#181825", crust="#11111b", s0="#313244", s1="#45475a", overlay="#6c7086",
                             text="#cdd6f4", accent="#cba6f7", green="#a6e3a1", red="#f38ba8", yellow="#f9e2af", blue="#89b4fa"),
    "Tokyo Night":      dict(bg="#1a1b26", mantle="#16161e", crust="#101014", s0="#292e42", s1="#3b4261", overlay="#565f89",
                             text="#c0caf5", accent="#bb9af7", green="#9ece6a", red="#f7768e", yellow="#e0af68", blue="#7aa2f7"),
    "Gruvbox Dark":     dict(bg="#282828", mantle="#1d2021", crust="#171717", s0="#3c3836", s1="#504945", overlay="#7c6f64",
                             text="#ebdbb2", accent="#d3869b", green="#b8bb26", red="#fb4934", yellow="#fabd2f", blue="#83a598"),
    "Nord":             dict(bg="#2e3440", mantle="#272c36", crust="#20242d", s0="#3b4252", s1="#434c5e", overlay="#616e88",
                             text="#d8dee9", accent="#b48ead", green="#a3be8c", red="#bf616a", yellow="#ebcb8b", blue="#81a1c1"),
}
ACCENTS = {"Padrão do tema": None, "Azul": "blue", "Verde": "green", "Amarelo": "yellow", "Vermelho": "red"}
CURSORES = ["Bloco", "Barra", "Sublinhado"]

def _mix(a, b, t):
    """mistura duas cores #rrggbb: t=0 -> a, t=1 -> b"""
    x = [int(a[i:i + 2], 16) for i in (1, 3, 5)]; y = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(p + (q - p) * t):02x}" for p, q in zip(x, y))

def ui_colors(term_cfg):
    """paleta da interface para o tema e a cor de destaque escolhidos"""
    ui = dict(THEME_UI.get(term_cfg.get("theme"), THEME_UI["Catppuccin Mocha"]))
    k = ACCENTS.get(term_cfg.get("accent"))
    if k: ui["accent"] = ui[k]
    return ui

def css_for(css_base, ui):
    """reescreve as cores do CSS padrão (Catppuccin) para a paleta `ui`, de uma vez só (sem trocas em cadeia)"""
    d = THEME_UI["Catppuccin Mocha"]
    m = {d[k]: ui[k] for k in d}
    if ui["bg"] != d["bg"]:                              # derivados; no tema padrão ficam como no CSS original
        m["#a6adc8"] = _mix(ui["text"], ui["bg"], .28)   # texto secundário
        m["#585b70"] = ui["s1"]
    if ui["accent"] != d["accent"]:
        m["#d9bdfa"] = _mix(ui["accent"], "#ffffff", .22)  # destaque em hover
    return re.sub(r"#[0-9a-fA-F]{6}", lambda mo: m.get(mo.group(0).lower(), mo.group(0)), css_base)

def _toml_val(v):
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, (int, float)): return repr(v)
    return json.dumps(str(v), ensure_ascii=False)

def save_config(cfg):
    """grava ~/.raid_point/config.toml (atômico)"""
    lines = ["# /dev/raid — configuração. Pode editar à mão, mas o painel de Configurações (Ctrl+,) faz isso por você.", ""]
    for sec, vals in cfg.items():
        if not isinstance(vals, dict): continue
        lines.append(f"[{sec}]")
        lines += [f"{k} = {_toml_val(v)}" for k, v in vals.items()]
        lines.append("")
    f = HOME / "config.toml"; tmp = Path(str(f) + ".tmp")
    HOME.mkdir(parents=True, exist_ok=True)
    tmp.write_text("\n".join(lines)); os.replace(tmp, f)

def load_config():
    """config.toml mesclado com os padrões; cria o arquivo na primeira vez."""
    import copy, tomllib
    base = copy.deepcopy(CONFIG_DEFAULT)
    f = HOME / "config.toml"
    if not f.exists():
        try: save_config(base)
        except OSError: pass
        return base
    try: user = tomllib.loads(f.read_text())
    except Exception as e:
        print("aviso: config.toml inválido, usando padrões:", e, file=__import__("sys").stderr); user = {}
    for sec, vals in user.items():
        if isinstance(vals, dict): base.setdefault(sec, {}).update(vals)
    return base

def save_agents(lst):
    clean = [{"name": a["name"].strip(), "cmd": a.get("cmd", "").strip()} for a in lst if a.get("name", "").strip()]
    write_json_atomic(CFG / "agents.json", clean or [{"name": "Shell", "cmd": ""}])


def _parse_projects(text):
    """JSON do projects.json; perdoa vírgula sobrando no fim de objeto/lista (erro comum de edição à mão)"""
    try: return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(re.sub(r",(\s*[}\]])", r"\1", text))      # se ainda falhar, levanta o erro original

def projects_error():
    """None se o projects.json está ok (ou não existe); senão a mensagem de erro"""
    try: _parse_projects(PROJ.read_text()); return None
    except FileNotFoundError: return None
    except Exception as e: return f"{type(e).__name__}: {e}"

def read_projects():
    """conteúdo bruto do projects.json (inclui metadados como _last); {} se faltar ou estiver ilegível (leitores)"""
    try: return _parse_projects(PROJ.read_text())
    except Exception: return {}

def load_projects():
    return {k: v for k, v in read_projects().items() if isinstance(v, dict)}

def update_projects(fn):
    """lê-modifica-grava o projects.json com trava e escrita atômica. Se o arquivo existir mas estiver
    ilegível, NÃO grava (evita apagar a lista inteira por causa de uma leitura ruim)."""
    with open(CFG / "projects.lock", "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try: d = _parse_projects(PROJ.read_text())
        except FileNotFoundError: d = {}
        r = fn(d)
        tmp = PROJ.with_suffix(".tmp"); tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False))
        os.replace(tmp, PROJ)
        return r if r is not None else d

def safe_name(s):
    """nome de projeto seguro: sem barras/caracteres estranhos e sem começar com '_' (reservado a metadados)"""
    return re.sub(r"[^\w .-]", "-", s or "").strip(" ._-") or "projeto"

def unique_name(base, taken_dir=None):
    """nome que não colide com outro projeto de outra pasta"""
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
    """projeto cujo diretório contém cwd (o mais específico)"""
    best, blen = None, -1
    cwd = os.path.realpath(cwd or ".")
    for n, p in load_projects().items():
        if p.get("host"):
            continue
        d = os.path.realpath(os.path.expanduser(p.get("dir", "")))
        for base in ((d, d + "-wt") if d else ()):             # <dir>-wt = worktrees dos agentes
            if (cwd == base or cwd.startswith(base + os.sep)) and len(d) > blen:
                best, blen = n, len(d)
    return best

def pdir(name):
    p = load_projects().get(name, {})
    return p.get("dir") if p.get("host") else os.path.expanduser(p.get("dir", "~"))

# ---------------------------------------------------------------- tmux
def sess(name):
    """nome da sessão tmux do projeto ('.' e ':' não podem ser endereçados pelo tmux)"""
    return re.sub(r"[.:]", "_", name)

def tgt(name):
    """alvo EXATO de janela/painel da sessão do projeto (sem '=' o tmux casa por prefixo: 'api' acharia 'api2')"""
    return f"={sess(name)}:"

def sess_t(name):
    """alvo exato de sessão (kill-session, has-session, attach...)"""
    return f"={sess(name)}"

def _q(args):
    """junta args para o shell remoto SEMPRE entre aspas (um '=nome' sem aspas viraria expansão no zsh)"""
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
    """comando que conecta (mosh/ssh) à sessão tmux do projeto remoto"""
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
        if f[1] in _HOSTS: f[1] = "Shell"           # título padrão do tmux = nome da máquina
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
    """cria um git worktree isolado para um agente; devolve (caminho, erro)"""
    p = load_projects().get(project, {})
    if p.get("host"): return None, "worktree isolado não funciona em projeto remoto"
    root = git_root(pdir(project) or "")
    if not root: return None, "o projeto não é um repositório git"
    if subprocess.run(["git", "-C", root, "rev-parse", "--verify", "-q", "HEAD"], capture_output=True).returncode != 0:
        return None, "o repositório ainda não tem nenhum commit (o worktree precisa de um)"
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "agente"
    base = Path(root).parent / f"{Path(root).name}-wt"
    base.mkdir(exist_ok=True)
    for i in range(1, 200):
        path, br = base / f"{slug}-{i}", f"agent/{slug}-{i}"
        if path.exists() or subprocess.run(["git", "-C", root, "show-ref", "--verify", "-q", f"refs/heads/{br}"],
                                           capture_output=True).returncode == 0:
            continue                                             # caminho ou branch já usados: tenta o próximo número
        r = subprocess.run(["git", "-C", root, "worktree", "add", "-b", br, str(path)], text=True, capture_output=True)
        return (str(path), None) if r.returncode == 0 else (None, (r.stderr or r.stdout).strip()[-300:])
    return None, "worktrees demais (limite 200 por agente)"

def spawn_pane(project, title, cmd="", worktree=False, layout="tiled", cwd=None):
    """abre um painel; devolve (pane_id, pasta, erro). Se pediu worktree e ele falhar, NÃO abre (nada de rodar sem isolamento)"""
    d = cwd or pdir(project)
    if worktree and not cwd:
        d, err = make_worktree(project, title)
        if err: return None, None, f"worktree: {err}"
    a = ["split-window", "-t", tgt(project), "-P", "-F", "#{pane_id}"] + (["-c", d] if d else [])
    if cmd: a.append(cmd)
    r = run_tmux(project, *a)
    pid = r.stdout.strip()
    if not pid: return None, d, (r.stderr or "tmux não criou o painel").strip()[-200:]
    run_tmux(project, "select-pane", "-t", pid, "-T", title)
    run_tmux(project, "select-layout", "-t", tgt(project), layout)
    return pid, d, None

# ---------------------------------------------------------------- orquestração
PROMPT_ARG = {"claude", "codex", "gemini", "cursor-agent", "opencode"}   # CLIs que aceitam a tarefa como argumento inicial

def agent_launch_cmd(ag, prompt=""):
    """(comando, precisa_send_keys). Claude/Codex & cia recebem a tarefa como argumento (confiável);
    os demais abrem vazios e a tarefa vai por send-keys depois. Preset pode forçar com "prompt": "arg"|"keys"."""
    cmd = (ag.get("cmd") or "").strip()
    if not cmd or not prompt: return cmd, False
    mode = ag.get("prompt")
    try: first = os.path.basename(shlex.split(cmd)[0])
    except (ValueError, IndexError): first = ""
    if mode == "arg" or (mode is None and first in PROMPT_ARG):
        return f"{cmd} {shlex.quote(prompt)}", False
    return cmd, True

def run_task(project, prompt, agents, worktree=True, layout="tiled"):
    """dispara a MESMA tarefa em vários agentes, cada um (opcionalmente) em worktree isolada.
    agents: lista de nomes de preset (repetir o nome = mais cópias). Devolve [{agent, pane, dir, error}]."""
    presets = {a["name"].lower(): a for a in agents_cfg()}
    out = []
    for nome in agents:
        ag = presets.get(nome.lower())
        if not ag or not ag.get("cmd"):
            out.append({"agent": nome, "pane": None, "dir": None, "error": "preset desconhecido ou sem comando"}); continue
        cmd, keys = agent_launch_cmd(ag, prompt)
        pid, d, err = spawn_pane(project, ag["name"], cmd, worktree, layout)
        if pid and keys:
            time.sleep(4)
            run_tmux(project, "send-keys", "-t", pid, "-l", prompt); run_tmux(project, "send-keys", "-t", pid, "Enter")
        out.append({"agent": ag["name"], "pane": pid, "dir": d, "error": err})
    return out

ORCHESTRATOR_PROMPT = (
    "Você é o ORQUESTRADOR deste projeto no /dev/raid. Quando eu te passar uma tarefa: "
    "1) divida em partes independentes (que não editem os mesmos arquivos); "
    "2) para cada parte, use a ferramenta MCP `spawn_agent` do servidor `raidpoint` com worktree=true e a instrução "
    "da parte em `prompt`; escolha o agente (Claude ou Codex) pelo tipo de trabalho e olhe `usage` para não estourar a cota; "
    "3) acompanhe com `list_agents` e `read_output`, e use `send_message` só para corrigir o rumo; "
    "4) quando todos terminarem, resuma o que cada um fez e liste as branches agent/* para eu revisar em Ctrl+G. "
    "NÃO faça merge nem push sozinho. Responda agora apenas confirmando que entendeu e aguarde a minha tarefa."
)

# ---------------------------------------------------------------- eventos
def log_event(ev):
    ev.setdefault("ts", time.time())
    with open(EVENTS, "a") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    try:                                                         # rotação: o arquivo não cresce para sempre
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
    if size > 1_000_000: lines = lines[1:]                       # a primeira linha pode ter sido cortada
    now = time.time(); out = []
    for l in lines[-limit:]:
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
    if project != safe_name(project) and project not in load_projects():
        raise ValueError("projeto inválido")
    d = MEMDIR / safe_name(project); d.mkdir(parents=True, exist_ok=True)
    kind, tags = re.sub(r"\s+", " ", kind or "note")[:30], re.sub(r"\s+", " ", tags or "")[:100]
    path = d / f"{time.strftime('%Y%m%d-%H%M%S')}-{slug}.md"
    i = 1
    while path.exists():                                         # duas notas no mesmo segundo não se sobrescrevem
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
    """pede aprovação humana ao app /dev/raid (diálogo). Sem app rodando = negado."""
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
    if load_projects().get(project, {}).get("host"):
        return {"error": "run_with_secrets só funciona em projetos locais"}
    have = secret_names(project)
    missing = [n for n in names if n not in have]
    if missing: return {"error": f"segredos inexistentes: {missing}"}
    detail = f"Comando: {command[:1500]}{'…' if len(command) > 1500 else ''}\nSegredos: {', '.join(names)}\nMotivo: {purpose or '(não informado)'}"
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

NWO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

def check_nwo(nwo):
    if not NWO_RE.match(nwo or "") or any(part in (".", "..") for part in nwo.split("/")):
        raise ValueError(f"repositório inválido: {nwo!r} (use dono/repo)")

def workspace_path(nwo):
    """~/.raid_point/workspaces/<repo> (se já existe outro repo com esse nome: <dono>-<repo>)"""
    check_nwo(nwo)
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
    try: r = subprocess.run(["gh", "repo", "clone", nwo, str(p)], text=True, capture_output=True, timeout=900)
    except subprocess.TimeoutExpired: return None, "o clone passou de 15 minutos e foi cancelado"
    return (str(p), None) if r.returncode == 0 else (None, (r.stderr or r.stdout).strip()[-400:])


# ---------------------------------------------------------------- uso de tokens (Claude Code, via transcripts)
CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
USAGE_STATE = CM / "usage.json"
BUCKET = 300  # segundos

def usage_update(max_age_days=8):
    """lê (incrementalmente) os transcripts do Claude Code e acumula tokens por balde de 5 min/projeto/modelo.
    Deduplica por message.id (uma resposta aparece em várias linhas do transcript)."""
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
    """totais por janela (5h, 24h, 7d), por projeto e por modelo. 'novos' = entrada + saída + criação de cache."""
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


# ---------------------------------------------------------------- limites do plano (vêm do statusLine do Claude Code)
PLAN_FILE = DATA / "plan.json"

def plan_status():
    """últimos percentuais de 5h/7d gravados pelo `raidpoint statusline`; janelas vencidas são descartadas"""
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
    """limites do plano do Codex (5h / semana), créditos e tipo de plano, lidos do último `token_count`
    com `rate_limits` nos logs ~/.codex/sessions (o Codex grava isso sozinho). None se não houver dados."""
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
    for k in ("primary", "secondary"):                       # janela que já reiniciou = dado vencido
        w = d.get(k)
        if w and w.get("resets_at") and w["resets_at"] < now: d[k] = None
    d["age_s"] = now - d["ts"]
    return d

# ---------------------------------------------------------------- git: últimos commits e CI (GitHub Actions)
_GD = {}

def ci_state(runs):
    if not runs: return "none"
    r = runs[0]
    if r["status"] != "completed": return "running"
    return {"success": "ok", "failure": "fail", "timed_out": "fail", "startup_failure": "fail"}.get(r["conclusion"], "other")

def git_detail(d, ncommits=6, nruns=6):
    """branch, últimos commits e últimas execuções do GitHub Actions da branch atual"""
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
    """pastas git do projeto: a principal + worktrees dos agentes -> [(rótulo, caminho)]"""
    r = _git(d, "worktree", "list", "--porcelain")
    if r.returncode != 0: return []
    paths = [l[9:] for l in r.stdout.splitlines() if l.startswith("worktree ")]
    out = []
    for i, p in enumerate(paths):
        out.append(("principal" if i == 0 else os.path.basename(p), p))
    return out

def git_changes(d):
    """arquivos alterados -> [(status, caminho)]; status: M modificado, A novo(staged), D apagado, ? novo, R renomeado"""
    r = _git(d, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if r.returncode != 0: return None
    out, parts, i = [], r.stdout.split("\0"), 0
    while i < len(parts):
        e = parts[i]; i += 1
        if len(e) < 4: continue
        xy, path = e[:2], e[3:]
        if "R" in xy or "C" in xy: i += 1          # próximo campo é o caminho de origem
        st = "?" if xy == "??" else ("D" if "D" in xy else ("A" if "A" in xy else ("R" if "R" in xy else "M")))
        out.append((st, path))
    return out

def git_diff(d, path, status):
    """diff de um arquivo (inclui o que já está staged); novos: mostra o conteúdo todo como adição"""
    if status == "?":
        r = _git(d, "diff", "--no-index", "--", os.devnull, path)    # sai com 1 quando há diferença
    else:
        r = _git(d, "diff", "HEAD", "--", path)
        if r.returncode != 0 or not r.stdout:                         # repo sem commits
            r = _git(d, "diff", "--cached", "--", path)
    txt = r.stdout
    return txt if len(txt) < 400_000 else txt[:400_000] + "\n… (diff truncado)"

def git_revert(d, path, status):
    """descarta as mudanças de UM arquivo; devolve mensagem de erro ou None"""
    if status == "?":
        f = Path(d, path)
        try: f.unlink()
        except OSError as e: return str(e)
        return None
    r = _git(d, "restore", "--source=HEAD", "--staged", "--worktree", "--", path)
    return None if r.returncode == 0 else (r.stderr.strip() or "falhou")

def git_commit(d, msg, paths=None):
    """commita os arquivos escolhidos (ou tudo); devolve (ok, saída)"""
    if not msg.strip(): return False, "mensagem vazia"
    r = _git(d, "add", "-A", "--", *(paths or ["."]))
    if r.returncode != 0: return False, r.stderr.strip()
    r = _git(d, "commit", "-m", msg, "--", *(paths or []) ) if paths else _git(d, "commit", "-m", msg)
    return r.returncode == 0, (r.stdout + r.stderr).strip()

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
