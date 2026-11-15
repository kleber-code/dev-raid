# Orchestrator (chat with your AI)

The orchestrator is the AI you talk to from /dev/raid. It is chosen in `~/.raid_point/config.toml`:

```toml
[orchestrator]
provider = "claude-code"      # or "http"
url = ""                      # http only: https://host/api
token_file = ""               # http only: path to a file holding the bearer token (chmod 600)
token_env = ""                # http only: ...or the name of an environment variable
```

## `claude-code` (default)

Runs headless Claude Code (`claude -p`) with your own login, limited to the `raidpoint` MCP tools, and the orchestrator
prompt. The conversation continues between messages (`--resume`). The text you type goes through stdin, never on the
command line. Claude Code's own approvals do not exist in headless mode, so tools that ask for approval in /dev/raid
(plain shells, secrets, plugins) still show the /dev/raid dialog.

## `http`: bring your own AI

Any service that speaks this small REST contract can be the orchestrator. All requests carry
`Authorization: Bearer <token>`. The URL must be `https` (plain `http` only for `localhost`), redirects are never followed
(they would carry the token to another host), responses are capped at 2 MB, and the token is read from a private file
(`chmod 600` is enforced) or an environment variable, never from `config.toml`.

| Request | Response |
|---|---|
| `POST {url}/chat` `{"text": "..."}` | `{"text": "..."}` |
| `GET {url}/history?limit=60` | `{"messages": [{"role": "user"\|"assistant", "text": "...", "ts": ...}]}` |
| `GET {url}/approvals` | `{"approvals": [{"id", "kind", "tool", "summary", "origin", "created"}]}` |
| `POST {url}/approvals/{id}/decide` `{"approve": true\|false}` | `{"ok": true}` |

- `history` and the approvals endpoints are optional: without them the chat just has no history and no approval buttons.
- **Streaming is optional.** If `chat` answers with `Content-Type: text/event-stream`, it is read as server-sent events:
  `data: {"delta": "..."}` pieces, then `data: {"done": true, "text": "<full answer>"}`; `data: {"error": "..."}` aborts.
  Otherwise the single JSON answer is used.
- Approval ids must match `[A-Za-z0-9_-]{1,40}`. Everything the service returns is shown as plain text.
- The AI acts on /dev/raid through the MCP server (`raidpoint mcp`) on its own side; this contract is only the chat.

## The chat panel

`Ctrl+Shift+K` (or the envelope button, or *Orchestrator: chat* in the palette) opens the panel on the right.

- The header says where your messages go. With `claude-code` the conversation is per project; with `http` it is whatever the
  service keeps.
- `Enter` sends, `Shift+Enter` inserts a new line. One message at a time per conversation.
- If the service lists pending approvals, they show above the conversation with **Approve** / **Reject** buttons (polled every
  5 s while the panel is open, and right after each answer).
- Errors (no token, service unreachable, HTTP 401...) appear in the conversation, not as dialogs.
- Everything the AI or the service sends is shown as plain text, never as markup.

`tests/smoke_chat_ui.py` exercises the panel against a fake provider on a headless Wayland display (instructions at the top).

## MCP catalog version

`tools/list` answers with `"_meta": {"devraid/catalogVersion": "1"}`. It changes only when a tool is renamed or its
parameters or output change shape, so integrations can pin to it. `tests/golden_tools.json` locks the catalog.
