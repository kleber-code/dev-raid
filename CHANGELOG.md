# Changelog

## 0.2.0 — 2026-11-13
- Marca **/dev/raid**, logo e ícone; comando único `devraid`; `app_id` `br.com.satela.DevRaid`.
- Instalador de uma linha (`curl | sh` / `wget | sh`), `make install`, PKGBUILD (AUR), spec RPM, metainfo AppStream.
- **Orquestração:** tarefa em paralelo (várias cópias/agentes em worktrees) e agente orquestrador; `spawn_agent` do MCP
  entrega a tarefa como argumento (sem `sleep`).
- **Créditos:** limite do plano e créditos do **Codex** (lidos dos logs dele) ao lado do Claude; `claude_plan` e `codex_plan` no MCP.
- **Aparência:** temas (Catppuccin, Tokyo Night, Gruvbox, Nord) aplicados à interface e ao tmux, cor de destaque, cursor, largura da lista.
- Seletor de fonte próprio (só monoespaçadas, com busca): o do GTK era lento e instável sem portal de desktop.
- Ações (`Ctrl+D`), Configurações visuais (`Ctrl+,`), Mudanças/diff/commit (`Ctrl+G`), zoom do texto.
- `projects.json` aceita vírgula sobrando e, se estiver ilegível, o app avisa em vez de mostrar a lista vazia.

## 0.1.0
- Primeira versão pública (como Raid Point).
