# Bridge: agents on ssh/mosh hosts talking to /dev/raid

An agent running on a remote project (ssh/mosh) cannot reach `raidpoint mcp` on your machine. The bridge fixes that:

    remote agent -> devraid-bridge (shim, stdio MCP) -> ~/.raid_point/bridge.sock (remote)
                 -> ssh -R reverse tunnel (opened from here) -> bridge socket here -> /dev/raid tools

mosh only carries the terminal, so the tunnel is a separate ssh connection that `raidpoint bridge up <host>` keeps alive
(reconnects with backoff). The GUI starts it automatically when you open a remote project.

## Setup (once per host)

    raidpoint bridge install <host>    # copies the shim and registers MCP server "raidpoint-bridge" in the remote Claude Code
    raidpoint bridge status            # bridges running here

## What a remote agent can do

`list_projects`, `list_agents`, `send_message`, `read_output`, `memory_*`, `secret_names`, `usage`, `ci_status`.
There is no inbox: after `send_message`, poll `read_output` on that pane. Calls default to the project bound to that host
(if several projects use the host, pass `project`).

Not available over the bridge: `spawn_agent`, `run_with_secrets`, `open_repo`, `list_repos`, plugins. The remote host is less
trusted than this machine. `send_message` to a plain shell still asks the human. Sockets are 0600 on both sides.
If the tunnel is down the shim answers with a clear "bridge offline" message instead of hanging.
