# Raid Point

Um "VS Code de terminais" para **orquestrar vários agentes de IA** (Claude Code, Codex, Aider…)
em paralelo, um conjunto de terminais por projeto, que **sobrevive** quando você fecha a janela
(tmux por baixo). GTK4 + VTE, feito em Python, pensado para Linux (sway/Wayland ou X11).

## O que faz

- **Projetos e Repos.** *Projetos* é o que você mexe; *Repos* lista **todos os seus repositórios do GitHub**
  (usuário + orgs, via `gh`). Abrir um repo o clona em `~/.raid_point/workspaces/<repo>` e o promove a projeto.
  Projetos exigem git.
- **Terminais persistentes.** Cada projeto é uma sessão tmux. Feche o app, volte, tudo continua lá.
- **Layouts claros:** colunas, linhas, grade, principal+lateral. Botão **＋ Agente** abre Claude/Codex/Aider/…
  num novo painel, opcionalmente em um **git worktree isolado** por agente.
- **Servidores remotos** (`~/.ssh/config`) via **mosh** ou ssh; o tmux roda na VPS.
- **Painel de agentes** (`Ctrl+J`): painéis, sessões de IA e **subagentes** (via hooks do Claude Code),
  com status; clique abre o transcript.
- **MCP (`raidpoint mcp`)**: agentes listam/criam/mensageiam outros agentes, leem saída, usam **memória** e
  **segredos** do projeto.
- **Memória** por projeto em markdown + busca FTS5; entra no contexto ao iniciar uma sessão do Claude Code.
- **Segredos**: ficam no chaveiro do sistema. O agente só vê os *nomes*; para usar, você aprova num
  diálogo e o valor entra só no ambiente do comando (saída mascarada).
- **Git/PR** no título (branch, alterações, PR e checks via `gh`).

## Instalar

```bash
git clone git@github.com:kleber-code/raid-point.git && cd raid-point
./install.sh          # lista dependências que faltam (comandos para Arch e Fedora)
gh auth login         # o app usa a autenticação do gh (nada de OAuth próprio)
raidpoint install     # registra hooks e MCP no Claude Code / Codex
raid-point            # abre o app
```

Dependências no Arch: `sudo pacman -S python-gobject gtk4 vte4 tmux github-cli libsecret gnome-keyring mosh noto-fonts`

## Atalhos (dentro dos terminais: prefixo `Ctrl+a`)

| Ação | Tecla |
|---|---|
| Ocultar/mostrar projetos | `Ctrl+B` |
| Painel de agentes | `Ctrl+J` |
| Dividir / nova aba / fechar painel / zoom | `Alt+\` , `Alt+-` / `Alt+t` / `Alt+w` / `Alt+z` |
| Navegar entre painéis | `Alt+setas` |

## Sway

O sway cuida das janelas; o Raid Point cuida de projetos/agentes. `app_id` = `dev.raidpoint.App`:

```
for_window [app_id="dev.raidpoint.App"] move to workspace 2
```

## Dados

Tudo em `~/.raid_point/`: `projects.json`, `agents.json` (presets do menu ＋ Agente), `tmux.conf`,
`workspaces/`, `data/` (eventos e memória).

## Segurança

`send_message`/`spawn_agent` em **shell puro** exigem aprovação humana; segredos nunca são retornados
a agentes. Alerta de vazamento de segredo em logs: ainda não implementado.
