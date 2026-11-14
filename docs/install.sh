#!/bin/sh
# /dev/raid — instalador.
#
#   curl -fsSL https://kleber-code.github.io/dev-raid/install.sh | sh
#   wget -qO-  https://kleber-code.github.io/dev-raid/install.sh | sh
#
# Opções (variáveis de ambiente, ou argumentos depois de `sh -s --`):
#   DEVRAID_REF=v0.2.0     versão (tag ou branch). Padrão: a última release; sem release, main
#   DEVRAID_PREFIX=...     onde instalar. Padrão: ~/.local (sem sudo). Ex.: /usr/local
#   DEVRAID_YES=1          não perguntar antes de instalar dependências do sistema
#   DEVRAID_SRC=/caminho   usar este checkout em vez de baixar (desenvolvimento/offline)
#   --uninstall            remove o /dev/raid (não apaga ~/.raid_point, onde ficam seus dados)
#
# Leia antes de rodar, se preferir:  curl -fsSL https://kleber-code.github.io/dev-raid/install.sh | less
set -eu

REPO="kleber-code/dev-raid"
PREFIX="${DEVRAID_PREFIX:-$HOME/.local}"
REF="${DEVRAID_REF:-}"
YES="${DEVRAID_YES:-0}"
SRC="${DEVRAID_SRC:-}"
ACTION="install"
for a in "$@"; do
  case "$a" in
    --uninstall) ACTION="uninstall" ;;
    --yes|-y) YES=1 ;;
    -h|--help) sed -n '2,15p' "$0" 2>/dev/null || true; exit 0 ;;
  esac
done

say()  { printf '\033[1;35m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33maviso:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merro:\033[0m %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

[ "$(uname -s)" = "Linux" ] || die "o /dev/raid roda em Linux (GTK4 + tmux)."

# ---------------------------------------------------------------- desinstalar
if [ "$ACTION" = "uninstall" ]; then
  say "removendo de $PREFIX"
  rm -rf "$PREFIX/lib/devraid"
  rm -f  "$PREFIX/bin/devraid" "$PREFIX/bin/raidpoint" "$PREFIX/share/applications/br.com.satela.DevRaid.desktop" \
         "$PREFIX/share/icons/hicolor/scalable/apps/devraid.svg" "$PREFIX/share/metainfo/br.com.satela.DevRaid.metainfo.xml"
  for s in 512 256 128 64 48 32 16; do rm -f "$PREFIX/share/icons/hicolor/${s}x${s}/apps/devraid.png"; done
  say "pronto. Seus dados continuam em ~/.raid_point (apague à mão se quiser)."
  exit 0
fi

# ---------------------------------------------------------------- baixar
download() {   # download URL DESTINO
  if have curl; then curl -fsSL "$1" -o "$2"
  elif have wget; then wget -qO "$2" "$1"
  else die "preciso de curl ou wget."; fi
}
fetch_stdout() {
  if have curl; then curl -fsSL "$1"; elif have wget; then wget -qO- "$1"; else die "preciso de curl ou wget."; fi
}

# ---------------------------------------------------------------- dependências
PY_OK=0
python3 -c 'import sys, gi; gi.require_version("Gtk","4.0"); gi.require_version("Vte","3.91"); sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null && PY_OK=1

faltando=""
[ "$PY_OK" = 1 ] || faltando="$faltando python3>=3.11+gtk4+vte"
for c in tmux gh secret-tool tar make; do have "$c" || faltando="$faltando $c"; done

if [ -n "$faltando" ]; then
  . /etc/os-release 2>/dev/null || true
  fam="${ID:-} ${ID_LIKE:-}"
  case "$fam" in
    *arch*)   PM="pacman -S --needed --noconfirm"; PKGS="python-gobject gtk4 vte4 tmux github-cli libsecret gnome-keyring mosh noto-fonts make" ;;
    *fedora*|*rhel*) PM="dnf install -y"; PKGS="python3-gobject gtk4 vte291-gtk4 tmux gh libsecret mosh make" ;;
    *debian*|*ubuntu*) PM="apt-get install -y"; PKGS="python3-gi gir1.2-gtk-4.0 gir1.2-vte-3.91 tmux gh libsecret-tools mosh make" ;;
    *) PM=""; PKGS="" ;;
  esac
  say "faltando:$faltando"
  if [ -z "$PM" ]; then
    die "não conheço o gerenciador de pacotes desta distro. Instale: GTK4, VTE 3.91 (com PyGObject), tmux, gh, libsecret (secret-tool), make — e rode de novo."
  fi
  SUDO=""; [ "$(id -u)" = 0 ] || { have sudo && SUDO="sudo" || die "preciso de root para instalar: $PKGS"; }
  say "vou rodar:  $SUDO $PM $PKGS"
  if [ "$YES" != 1 ]; then
    if [ -r /dev/tty ]; then
      printf 'Continuar? [S/n] ' > /dev/tty; read -r r < /dev/tty || r=n
      case "$r" in n|N|nao|não) die "cancelado. Instale as dependências e rode de novo." ;; esac
    else die "sem terminal para confirmar. Rode com DEVRAID_YES=1 ou instale as dependências antes."; fi
  fi
  # shellcheck disable=SC2086
  $SUDO $PM $PKGS
fi

# ---------------------------------------------------------------- obter o código
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
if [ -n "$SRC" ]; then
  [ -f "$SRC/Makefile" ] || die "DEVRAID_SRC=$SRC não parece o código do /dev/raid."
  DIR="$SRC"; say "usando $DIR"
else
  if [ -z "$REF" ]; then
    REF="$(fetch_stdout "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null \
           | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -n1 || true)"
    [ -n "$REF" ] || REF="main"
  fi
  say "baixando $REPO @ $REF"
  download "https://codeload.github.com/$REPO/tar.gz/$REF" "$TMP/src.tar.gz"
  tar -xzf "$TMP/src.tar.gz" -C "$TMP"
  DIR="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n1)"
  [ -f "$DIR/Makefile" ] || die "o pacote baixado não tem Makefile (ref '$REF' existe?)."
fi

# ---------------------------------------------------------------- instalar
say "instalando em $PREFIX"
make -s -C "$DIR" install PREFIX="$PREFIX"
have update-desktop-database && update-desktop-database "$PREFIX/share/applications" >/dev/null 2>&1 || true
have gtk-update-icon-cache && gtk-update-icon-cache -q -t "$PREFIX/share/icons/hicolor" >/dev/null 2>&1 || true

case ":$PATH:" in
  *":$PREFIX/bin:"*) ;;
  *) warn "$PREFIX/bin não está no seu PATH. Adicione ao seu shell:  export PATH=\"$PREFIX/bin:\$PATH\"" ;;
esac

printf '\n\033[1;32m/dev/raid instalado.\033[0m  Próximos passos:\n\n'
printf '  gh auth login        # uma vez (lista de repositórios, CI e PRs)\n'
printf '  devraid install      # registra hooks e MCP no Claude Code e no Codex\n'
printf '  devraid              # abre o app\n\n'
printf 'Documentação: https://kleber-code.github.io/dev-raid/guia.html\n'
printf 'Desinstalar:  curl -fsSL https://kleber-code.github.io/dev-raid/install.sh | sh -s -- --uninstall\n'
