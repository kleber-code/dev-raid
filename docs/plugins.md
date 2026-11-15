# Plugins

A /dev/raid plugin is an **MCP server running as its own process** (stdio, JSON-RPC 2.0). `raidpoint mcp` starts the
enabled plugins and merges their tools into its own catalog as `<plugin>__<tool>`, so Claude Code, Codex or any
orchestrator sees a single server. Plugins can be written in any language and live outside this repository.

## Layout

```
~/.raid_point/plugins/<name>/
  plugin.toml      manifest (below)
  ...              your server and anything it needs
```

```toml
name = "hello"                      # must match the directory name (a-z, 0-9, '-')
version = "0.1.0"
description = "What it does"
command = ["python3", "./server.py"]    # ./paths are relative to the plugin directory; run with that cwd
permissions = []                    # scopes you ask for on the /dev/raid API (shown when enabling)
env_passthrough = ["MY_API_TOKEN"]  # environment variables the plugin may see
```

A complete example is in [`examples/plugins/hello`](../examples/plugins/hello).

## Managing plugins

```
raidpoint plugin ls                 list plugins and their state
raidpoint plugin info <name>        manifest, command, permissions, sha256
raidpoint plugin enable <name>      shows the command it will run and asks for confirmation (--yes to skip)
raidpoint plugin disable <name>
raidpoint plugin tools <name>       start it and list its tools (and which ones ask for approval)
```

States: `disabled` (default), `enabled`, `changed` (the manifest was edited after you enabled it: it is not loaded
until you enable it again) and `invalid`. Plugin stderr goes to `~/.raid_point/cache/plugin-<name>.log`.

## What the core guarantees

- **Nothing runs until you enable it**, and enabling records the sha256 of `plugin.toml`.
- **Minimal environment:** the process gets `PATH`, `HOME`, `LANG`, `LC_ALL`, `XDG_RUNTIME_DIR`, `RAIDPOINT_HOME`,
  `RAIDPOINT_PLUGIN` and the variables in `env_passthrough` — not the rest of your environment.
- **Approval per call:** a tool without `annotations.readOnlyHint = true` makes the app ask you before every call
  (dialog "A plugin wants to run a tool", with the arguments). No app running means denied.
- **Untrusted output:** everything a plugin returns is capped at 60 000 characters, stripped of non-text parts and
  fenced in `<plugin-output plugin="...">` with a note telling the agent to treat it as data.
- **Failures are contained:** a plugin that crashes, hangs on startup (10 s) or on a call (120 s) is reported and skipped;
  the rest of the server keeps working.

## What it does not guarantee

- `readOnlyHint` is the plugin's own claim, and the manifest hash does not cover the plugin's other files. Enabling a
  plugin means trusting its code as you would trust any program you install. Only enable plugins you trust.
- `permissions` is declared and displayed, but **not enforced yet**: it will scope the token that plugins use to call the
  /dev/raid API (planned together with `devraid serve`).
- A plugin runs with your user's privileges; there is no sandbox.

## Tests

```
python3 -m unittest discover -s tests
```
