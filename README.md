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

## Atalhos

Teclado e mouse (o prefixo do tmux é `Ctrl+a`):

| Ação | Tecla / gesto |
|---|---|
| Copiar / colar | `Ctrl+Shift+C` / `Ctrl+Shift+V` (ou `Ctrl+Insert` / `Shift+Insert`) |
| Copiar dentro do tmux | arrastar com o mouse (vai sozinho para a área de transferência) |
| Abrir link | `Ctrl+clique` |
| Menu do botão direito | copiar, colar, abrir link, dividir, zoom, mover para nova aba, fechar painel |
| Ocultar/mostrar projetos | `Ctrl+B` |
| Painel de agentes | `Ctrl+J` |
| **Ações** (paleta: agentes, painéis, layout, texto, config…) | `Ctrl+D` |
| **Configurações** (visual: fonte, tema, atalhos, agentes) | `Ctrl+,` |
| Ir para a aba N / trocar painel de lugar | `Alt+1…9` / `Alt+Shift+setas` |
| Mudanças / diff / commit | `Ctrl+G` |
| Zoom do texto | `Ctrl +` / `Ctrl −` / `Ctrl 0` / `Ctrl`+roda (configurável em `~/.raid_point/config.toml`) |
| Dividir lado a lado / embaixo | `Alt+\` / `Alt+-` |
| Nova aba / próxima / anterior | `Alt+t` / `Ctrl+PageDown` / `Ctrl+PageUp` |
| Fechar painel (pergunta antes) / zoom | `Alt+w` / `Alt+z` |
| Navegar entre painéis | `Alt+setas` |

O botão direito é do Raid Point (e não do tmux ou do programa dentro do terminal), por isso funciona em qualquer painel.

## Sway

O sway cuida das janelas; o Raid Point cuida de projetos/agentes. `app_id` = `dev.raidpoint.App`:

```
for_window [app_id="dev.raidpoint.App"] move to workspace 2
```

## Dados

Tudo em `~/.raid_point/`: `projects.json`, `agents.json` (presets do menu ＋ Agente), `tmux.conf`,
`workspaces/`, `data/` (eventos e memória).

## Segurança e limites (leia)

- `send_message` só entra direto em painéis de **agente** (aberto pelo Raid Point, com o nome de um preset que
  não seja Shell). Qualquer outro painel (shell, ssh, python…) pede a sua aprovação.
- Os segredos ficam no chaveiro do sistema; as ferramentas MCP **nunca devolvem o valor** ao agente, e o
  `run_with_secrets` só roda depois da sua aprovação, com a saída mascarada (só mascara o valor exato, não
  versões codificadas dele).
- **Isso protege contra o uso pelas ferramentas MCP, não contra um agente com acesso a shell.** Um agente que roda
  comandos como o seu usuário consegue, em tese, ler o chaveiro direto (`secret-tool`) ou editar os arquivos de
  aprovação. Para uma barreira de verdade, rode os agentes sob outro usuário ou em sandbox.
- A memória do projeto entra no contexto de novas sessões: trate o que os agentes gravam nela como não confiável.
- Alerta de vazamento de segredo em logs: ainda não implementado.

## Desenvolvimento

- `RAIDPOINT_HOME` muda a pasta de dados e `RAIDPOINT_SOCKET` o socket do tmux, para testar sem tocar no uso real.
- Os nomes de sessão do tmux trocam `.` e `:` por `_` e os alvos usam `=nome:` (casamento exato, não por prefixo).
- `projects.json` é gravado com trava e de forma atômica; se estiver ilegível, o app se recusa a sobrescrevê-lo.
