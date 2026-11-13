#!/usr/bin/env bash
# Instala o Raid Point: links em ~/.local/bin + entrada no menu. Dados ficam em ~/.raid_point
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin"
mkdir -p "$BIN" "$HOME/.local/share/applications" "$HOME/.raid_point"
ln -sf "$DIR/bin/raid-point" "$BIN/raid-point"
ln -sf "$DIR/bin/raidpoint" "$BIN/raidpoint"
sed "s|@BIN@|$BIN|" "$DIR/desktop/raid-point.desktop" > "$HOME/.local/share/applications/raid-point.desktop"

falta=()
for c in tmux gh secret-tool; do command -v "$c" >/dev/null || falta+=("$c"); done
python3 -c 'import gi; gi.require_version("Gtk","4.0"); gi.require_version("Vte","3.91")' 2>/dev/null || falta+=("gtk4+vte (python-gobject, gtk4, vte4)")
command -v mosh >/dev/null || echo "aviso: mosh não instalado (projetos remotos cairão para ssh)"
if ((${#falta[@]})); then
  echo "faltando: ${falta[*]}"
  echo "Arch:   sudo pacman -S python-gobject gtk4 vte4 tmux github-cli libsecret gnome-keyring mosh noto-fonts"
  echo "Fedora: sudo dnf install python3-gobject gtk4 vte291-gtk4 tmux gh libsecret mosh"
fi
echo "ok. Próximos passos:  gh auth login   |   raidpoint install   (hooks + MCP)   |   raid-point"
