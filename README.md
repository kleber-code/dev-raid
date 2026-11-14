# /dev/raid

> Run many AI coding agents side by side — one persistent terminal workspace per project (GTK4 + VTE + tmux).

**[Website](https://kleber-code.github.io/dev-raid/)** · **[Full guide](https://kleber-code.github.io/dev-raid/guide.html)** · MIT

![/dev/raid with four panes and the agents panel](docs/img/main.webp)

A "VS Code for terminals" to **orchestrate many AI coding agents** (Claude Code, Codex, Aider…)
in parallel, one set of terminals per project, that **survives** when you close the window
(tmux under the hood). GTK4 + VTE, written in Python, made for Linux (sway/Wayland or X11).

## What it does

- **Projects and Repos.** *Projects* is what you're working on; *Repos* lists **all your GitHub repositories**
  (user + orgs, via `gh`). Opening a repo clones it into `~/.raid_point/workspaces/<repo>` and promotes it to a project.
  Projects must be git repositories.
- **Persistent terminals.** Each project is a tmux session. Close the app, come back, everything is still there.
- **Simple layouts:** columns, rows, grid, main+side. The **＋ Agent** button opens Claude/Codex/Aider/…
  in a new pane, optionally in an **isolated git worktree** per agent. Agents start in an interactive login shell,
  so CLIs in `~/.local/bin`, nvm, etc. are found even when the app is launched from the desktop menu; when an agent
  exits, the pane drops to a shell instead of closing.
- **Remote servers** (`~/.ssh/config`) via **mosh** or ssh; tmux runs on the VPS.
- **Parallel tasks and orchestrator:** the same task across several agents, each in its own worktree, or a Claude
  that splits the work and opens subagents over MCP. You review in **Changes** (`Ctrl+G`); nothing is merged on its own.
- **Credits:** plan usage (5-hour and weekly) for **Claude** and **Codex**, credit balance and tokens per project.
- **Agents panel** (`Ctrl+J`): panes, AI sessions and **subagents** (via Claude Code hooks),
  with status; click to open the transcript.
- **MCP (`raidpoint mcp`)**: agents list/spawn/message other agents, read output, and use project **memory** and
  **secrets**.
- **Memory** per project in markdown + FTS5 search; loaded into context when a Claude Code session starts.
- **Secrets**: stored in the system keyring. Agents only see the *names*; to use one, you approve it in a
  dialog and the value goes only into that command's environment (output masked).
- **Git/PR** in the title bar (branch, changes, PR and checks via `gh`).
- **Automatic updates** (see below).

## Install

One line (detects Arch, Fedora and Debian/Ubuntu, installs whatever is missing and puts the app in `~/.local`, no root):

```bash
curl -fsSL https://kleber-code.github.io/dev-raid/install.sh | sh
# or
wget -qO- https://kleber-code.github.io/dev-raid/install.sh | sh
```

Then: `gh auth login` (once), `devraid install` (registers hooks and MCP in Claude Code and Codex) and `devraid` to open it.
Running a script from the internet means trusting it: [read install.sh](docs/install.sh) first or pin a version with `DEVRAID_REF=v0.2.0`.
To remove: `curl -fsSL https://kleber-code.github.io/dev-raid/install.sh | sh -s -- --uninstall`.

**Packages** (in [`packaging/`](packaging)): a `PKGBUILD` for the AUR (`devraid` and `devraid-git`) and `devraid.spec` for RPM,
both ready but **not published yet**. By hand: `sudo make install PREFIX=/usr/local`.

Dependencies: Python 3.11+, GTK4, VTE 3.91 with PyGObject, tmux, `gh`, libsecret; `mosh` is optional.

## Updates

The app checks for a new version every few hours:

- **git checkout** — fast-forwarded to the new commits (never over local changes);
- **one-line install** (`curl | sh`) — the latest GitHub release is reinstalled in the same prefix;
- **distro package** (AUR/RPM) — left to your package manager.

Update by hand with `devraid update` (or `raidpoint update`; `--check` only checks). The palette has
**Check for updates** and **Restart /dev/raid** — terminals survive a restart because tmux runs its own server.
Turn it off in **Settings → Advanced → Automatic updates** or with `[updates] auto = false` in `~/.raid_point/config.toml`.

## Shortcuts

Keyboard and mouse (the tmux prefix is `Ctrl+a`):

| Action | Key / gesture |
|---|---|
| Copy / paste | `Ctrl+Shift+C` / `Ctrl+Shift+V` (or `Ctrl+Insert` / `Shift+Insert`) |
| Copy inside tmux | drag with the mouse (goes straight to the clipboard) |
| Open link | `Ctrl+click` |
| Right-click menu | copy, paste, open link, split, zoom, move to new tab, close pane |
| Hide/show projects | `Ctrl+B` |
| Agents panel | `Ctrl+J` |
| **Actions** (palette: agents, panes, layout, text, settings…) | `Ctrl+D` |
| **Settings** (look: font, theme, shortcuts, agents) | `Ctrl+,` |
| Go to tab N / swap pane position | `Alt+1…9` / `Alt+Shift+arrows` |
| Changes / diff / commit | `Ctrl+G` |
| Text zoom | `Ctrl +` / `Ctrl −` / `Ctrl 0` / `Ctrl`+scroll (configurable in `~/.raid_point/config.toml`) |
| Split side by side / below | `Alt+\` / `Alt+-` |
| New tab / next / previous | `Alt+t` / `Ctrl+PageDown` / `Ctrl+PageUp` |
| Close pane (asks first) / zoom | `Alt+w` / `Alt+z` |
| Move between panes | `Alt+arrows` |

The right-click menu belongs to /dev/raid (not to tmux or the program inside the terminal), so it works in any pane.

## Sway

Sway handles windows; /dev/raid handles projects/agents. `app_id` = `br.com.satela.DevRaid`:

```
for_window [app_id="br.com.satela.DevRaid"] move to workspace 2
```

## Internal names

The app used to be called Raid Point. The command is `devraid` (no arguments opens the window; with a verb it's the CLI: `devraid ls`, `devraid mcp`…) and the `app_id` is `br.com.satela.DevRaid`. The old `raidpoint` command, the `~/.raid_point` folder and the `raidpoint` MCP server were kept so existing installs don't break.

## Data

Everything lives in `~/.raid_point/`: `config.toml`, `projects.json`, `agents.json` (presets for the ＋ Agent menu), `tmux.conf`,
`workspaces/`, `data/` (events and memory).

## Security and limits (read this)

- `send_message` only writes directly into **agent** panes (opened by /dev/raid, named after a preset other
  than Shell). Any other pane (shell, ssh, python…) asks for your approval.
- Secrets live in the system keyring; the MCP tools **never return the value** to the agent, and
  `run_with_secrets` only runs after your approval, with the output masked (only the exact value is masked, not
  encoded versions of it).
- **This protects against use through the MCP tools, not against an agent with shell access.** An agent that runs
  commands as your user could, in theory, read the keyring directly (`secret-tool`) or edit the approval
  files. For a real barrier, run agents as a different user or in a sandbox.
- Project memory goes into the context of new sessions: treat whatever agents write there as untrusted.
- Alerts for secrets leaking into logs: not implemented yet.

## Development

- `RAIDPOINT_APPID` changes the app ID (to run a second test instance); `RAIDPOINT_SHOW=changes|palette|settings|parallel` opens a window at startup; `RAIDPOINT_HOME` changes the data folder and `RAIDPOINT_SOCKET` the tmux socket, so you can test without touching your real setup.
- tmux session names replace `.` and `:` with `_`, and targets use `=name:` (exact match, not prefix match).
- `projects.json` is written atomically with a lock; if it's unreadable, the app refuses to overwrite it.
