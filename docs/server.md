# /dev/raid on a server (24/7, no app)

A server install has no window: it is the `devraid` CLI, the Claude Code/Codex hooks, the MCP server, the project memory and the
briefing. Agents run in tmux sessions that survive disconnects and come back after a reboot.

## Install

    curl -fsSL https://kleber-code.github.io/dev-raid/install.sh | sh -s -- --headless

Needs only python3 (3.11+), tmux and git (`gh` is optional: repository list and CI). It installs into `~/.local` of the user that
runs it, with no sudo. **Install it as an unprivileged user dedicated to development, never as root**: agents run commands, and
whatever that user can reach, they can reach.

    devraid install       # hooks + MCP in Claude Code and Codex
    devraid doctor        # what is missing

## Projects and what runs in them

    devraid add api ~/code/api
    devraid startup api Claude "npm run dev"     # agent presets (agents.json) or commands; one pane each
    devraid startup api                          # show;  --clear empties it
    devraid up                                   # start (detached) every project that has a startup list
    devraid up api | devraid up --all            # one project | every local project
    devraid api                                  # attach;  devraid ls shows what is running

`up` never touches a session that is already running, so it is safe to run again. A project with `"autostart": true` in
`projects.json` gets an empty session. To make an agent pick up where it stopped after a reboot, use a preset whose command
resumes (for Claude Code: `claude --continue`).

## Back after a reboot

    devraid service install      # systemd user unit that runs `devraid up` at boot
    devraid service status

It also turns on *linger* for the user, which is what lets its services start at boot without a login. If that needs root on your
system, the command tells you what to run (`loginctl enable-linger <user>`). Removing the unit (`service remove`) or stopping it
never kills running sessions.

## Approvals without a window

A plain shell opened by an agent, text typed into a shell, a secret being used, a plugin tool that is not read-only: all of these
wait for a human. On a server:

    devraid approvals --watch    # asks y/N as requests arrive
    devraid approvals            # list;  devraid approve <id> | devraid deny <id>

Nobody answering within 2 minutes means **denied**. That is the point: an unattended server never grants itself anything.

## Secrets without a keyring

Servers rarely have a Secret Service. Choose the file backend:

    devraid config secrets.backend file

Secrets then live in `~/.raid_point/secrets/<project>.json`, mode 0600 inside a 0700 folder: plain text, protected by file
permissions only, like a `.env`. Anyone who becomes that user (or root) can read them, so keep production credentials out of a
development server. From your desktop, `raidpoint secret sync <host>` copies your secrets over ssh into whichever backend the
server uses. Agents still only ever see names; `run_with_secrets` still asks.

## Working from your desktop

Add the server as a remote project in the app (ssh or mosh). The panes you see are the server's tmux; `raidpoint bridge install
<host>` lets the agents there use your desktop's /dev/raid (other agents, memory). See [bridge.md](bridge.md).

## Agents and git

An agent that works while you sleep must leave its work somewhere you can see it. Every briefing tells agents to commit in small
steps and push the branch they are on (`[agents] git`); add your own rules with:

    devraid config agents.rules "Commit messages in English. Never touch infra/."

Give the server user a deploy key (or a fine-grained token) that can push only to the repositories it works on.

## Security checklist

- A dedicated unprivileged user: not root, not in `sudo`, not in the `docker` group (that group is root).
- Its own ssh key for GitHub, limited to the repositories it needs.
- No production secrets in its `~/.raid_point/secrets`.
- `devraid doctor` clean, and updates on (`devraid update`, or `updates.auto`).
