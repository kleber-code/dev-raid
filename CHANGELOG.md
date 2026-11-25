# Changelog

## Unreleased
- **Runs on a server, without the app:** `install.sh --headless` installs only the CLI, hooks and MCP (python3, tmux and git; no GTK).
  `raidpoint startup <project> <agent|command>…` says what should run in a project, `raidpoint up` starts those sessions detached,
  and `raidpoint service install` brings them back after a reboot (systemd user unit + linger). Requests from agents are answered
  in the terminal (`raidpoint approvals [--watch]`, `approve|deny <id>`), secrets can live in owner-only files where there is no
  keyring (`[secrets] backend = "file"`), and `raidpoint config` edits settings. `doctor` and `update` know a server install.
  See `docs/server.md`.
- **Agents commit and push:** every briefing (and the AGENTS.md block) now carries a git protocol: small commits, nothing left
  uncommitted or unpushed, never force-push. `[agents] git = "push" | "commit" | "off"`, plus `[agents] rules` for your own
  house rules, told to every agent.
- **Bridge:** agents running on an ssh/mosh host can use /dev/raid on your machine (talk to other agents, read their output,
  project memory) through a reverse tunnel with a restricted tool list. `raidpoint bridge install|up|status`; the app opens the
  tunnel when you open a remote project. See `docs/bridge.md`.
- **Fix stray floating shells:** tmux 3.8 binds Ctrl+drag (and `prefix *`, `prefix Tab`, the empty-area right-click menu) to floating panes,
  which fired by accident on Ctrl+click/drag. The default `tmux.conf` now unbinds them. Existing installs keep their own
  `~/.raid_point/tmux.conf`: append the `unbind` block from `config/tmux.conf`.
- **Orchestrator:** choose the AI you chat with (`[orchestrator]` in config.toml): headless Claude Code, or any service that speaks
  the small REST contract in `docs/orchestrator.md` (bearer token from a private file, https only, no redirects, optional SSE).
- **Orchestrator chat panel** (`Ctrl+Shift+K`) with the approvals the AI is waiting for (approve / reject).
- **AIs know about secrets:** Claude Code sessions are told the secret *names* of the project at start and what was added or removed
  on the next prompt (never values); `raidpoint mcp` now ships usage instructions to every MCP client. The orchestrator token can come
  from a Project secret (`token_secret = "project/NAME"`).
- **MCP catalog:** tools moved to `raidpoint/tools.py` (no change to names, parameters or output); `tools/list` now carries
  `_meta.devraid/catalogVersion`, and `tests/golden_tools.json` locks the catalog.
- **Plugins:** out-of-process MCP plugins in `~/.raid_point/plugins/<name>/plugin.toml`, merged into `raidpoint mcp` as
  `<plugin>__<tool>`. Off until enabled (`raidpoint plugin enable`), tied to the manifest hash, minimal environment, approval for
  every non-read-only call, untrusted-output fencing. See `docs/plugins.md` and `examples/plugins/hello`.
- **English everywhere:** interface, CLI, installer, website and docs are now in English. The guide moved to
  `guide.html` (the old `guia.html` redirects).
- **Automatic updates:** `devraid update` (or `raidpoint update`; `--check` only checks). The app checks every few hours:
  git checkouts are fast-forwarded (never over local changes), `curl | sh` installs get the latest GitHub release
  reinstalled in the same prefix, and distro packages (AUR/RPM) are left to the package manager. Toggle in
  Settings → Advanced → Automatic updates, or `[updates] auto = false` in `~/.raid_point/config.toml`.
  New palette commands: *Check for updates* and *Restart /dev/raid* (terminals survive the restart).
- **Fix:** agent presets (Claude, Codex, Aider, Ollama…) now start in an interactive login shell, so CLIs in
  `~/.local/bin`, nvm, etc. are found even when the app is launched from the desktop menu. When the agent exits,
  the pane drops to a shell instead of closing.

## 0.2.0 — 2026-11-13
- **/dev/raid** branding, logo and icon; single `devraid` command; `app_id` `br.com.satela.DevRaid`.
- One-line installer (`curl | sh` / `wget | sh`), `make install`, PKGBUILD (AUR), RPM spec, AppStream metainfo.
- **Orchestration:** parallel tasks (several copies/agents in worktrees) and an orchestrator agent; the MCP `spawn_agent`
  hands over the task as an argument (no `sleep`).
- **Credits:** plan limit and credits for **Codex** (read from its logs) next to Claude; `claude_plan` and `codex_plan` in MCP.
- **Appearance:** themes (Catppuccin, Tokyo Night, Gruvbox, Nord) applied to the interface and to tmux, accent color, cursor, sidebar width.
- Custom font picker (monospace only, with search): GTK's was slow and unstable without a desktop portal.
- Actions (`Ctrl+D`), visual Settings (`Ctrl+,`), Changes/diff/commit (`Ctrl+G`), text zoom.
- `projects.json` tolerates trailing commas and, if it's unreadable, the app warns instead of showing an empty list.

## 0.1.0
- First public release (as Raid Point).
