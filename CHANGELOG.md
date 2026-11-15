# Changelog

## Unreleased
- **Orchestrator:** choose the AI you chat with (`[orchestrator]` in config.toml): headless Claude Code, or any service that speaks
  the small REST contract in `docs/orchestrator.md` (bearer token from a private file, https only, no redirects, optional SSE).
- **Orchestrator chat panel** (`Ctrl+Shift+K`) with the approvals the AI is waiting for (approve / reject).
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
