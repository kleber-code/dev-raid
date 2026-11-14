#!/bin/sh
# /dev/raid — installer.
#
#   curl -fsSL https://kleber-code.github.io/dev-raid/install.sh | sh
#   wget -qO-  https://kleber-code.github.io/dev-raid/install.sh | sh
#
# Options (environment variables, or arguments after `sh -s --`):
#   DEVRAID_REF=v0.2.0     version (tag or branch). Default: the latest release; if none, main
#   DEVRAID_PREFIX=...     where to install. Default: ~/.local (no sudo). E.g.: /usr/local
#   DEVRAID_YES=1          do not ask before installing system dependencies
#   DEVRAID_SRC=/path      use this checkout instead of downloading (development/offline)
#   --uninstall            remove /dev/raid (does not delete ~/.raid_point, where your data lives)
#
# Read it before running, if you prefer:  curl -fsSL https://kleber-code.github.io/dev-raid/install.sh | less
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
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

[ "$(uname -s)" = "Linux" ] || die "/dev/raid runs on Linux (GTK4 + tmux)."

# ---------------------------------------------------------------- uninstall
if [ "$ACTION" = "uninstall" ]; then
  say "removing from $PREFIX"
  rm -rf "$PREFIX/lib/devraid"
  rm -f  "$PREFIX/bin/devraid" "$PREFIX/bin/raidpoint" "$PREFIX/share/applications/br.com.satela.DevRaid.desktop" \
         "$PREFIX/share/icons/hicolor/scalable/apps/devraid.svg" "$PREFIX/share/metainfo/br.com.satela.DevRaid.metainfo.xml"
  for s in 512 256 128 64 48 32 16; do rm -f "$PREFIX/share/icons/hicolor/${s}x${s}/apps/devraid.png"; done
  say "done. Your data is still in ~/.raid_point (delete it by hand if you want)."
  exit 0
fi

# ---------------------------------------------------------------- download
download() {   # download URL DEST
  if have curl; then curl -fsSL "$1" -o "$2"
  elif have wget; then wget -qO "$2" "$1"
  else die "curl or wget is required."; fi
}
fetch_stdout() {
  if have curl; then curl -fsSL "$1"; elif have wget; then wget -qO- "$1"; else die "curl or wget is required."; fi
}

# ---------------------------------------------------------------- dependencies
PY_OK=0
python3 -c 'import sys, gi; gi.require_version("Gtk","4.0"); gi.require_version("Vte","3.91"); sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null && PY_OK=1

missing=""
[ "$PY_OK" = 1 ] || missing="$missing python3>=3.11+gtk4+vte"
for c in tmux gh secret-tool tar make; do have "$c" || missing="$missing $c"; done

if [ -n "$missing" ]; then
  . /etc/os-release 2>/dev/null || true
  fam="${ID:-} ${ID_LIKE:-}"
  case "$fam" in
    *arch*)   PM="pacman -S --needed --noconfirm"; PKGS="python-gobject gtk4 vte4 tmux github-cli libsecret gnome-keyring mosh noto-fonts make" ;;
    *fedora*|*rhel*) PM="dnf install -y"; PKGS="python3-gobject gtk4 vte291-gtk4 tmux gh libsecret mosh make" ;;
    *debian*|*ubuntu*) PM="apt-get install -y"; PKGS="python3-gi gir1.2-gtk-4.0 gir1.2-vte-3.91 tmux gh libsecret-tools mosh make" ;;
    *) PM=""; PKGS="" ;;
  esac
  say "missing:$missing"
  if [ -z "$PM" ]; then
    die "unknown package manager for this distro. Install: GTK4, VTE 3.91 (with PyGObject), tmux, gh, libsecret (secret-tool), make — then run again."
  fi
  SUDO=""; [ "$(id -u)" = 0 ] || { have sudo && SUDO="sudo" || die "root is required to install: $PKGS"; }
  say "will run:  $SUDO $PM $PKGS"
  if [ "$YES" != 1 ]; then
    if [ -r /dev/tty ]; then
      printf 'Continue? [Y/n] ' > /dev/tty; read -r r < /dev/tty || r=n
      case "$r" in n|N|no|No|NO) die "cancelled. Install the dependencies and run again." ;; esac
    else die "no terminal to confirm. Run with DEVRAID_YES=1 or install the dependencies first."; fi
  fi
  # shellcheck disable=SC2086
  $SUDO $PM $PKGS
fi

# ---------------------------------------------------------------- get the code
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
if [ -n "$SRC" ]; then
  [ -f "$SRC/Makefile" ] || die "DEVRAID_SRC=$SRC does not look like the /dev/raid source."
  DIR="$SRC"; say "using $DIR"
else
  if [ -z "$REF" ]; then
    REF="$(fetch_stdout "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null \
           | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -n1 || true)"
    [ -n "$REF" ] || REF="main"
  fi
  say "downloading $REPO @ $REF"
  download "https://codeload.github.com/$REPO/tar.gz/$REF" "$TMP/src.tar.gz"
  tar -xzf "$TMP/src.tar.gz" -C "$TMP"
  DIR="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n1)"
  [ -f "$DIR/Makefile" ] || die "the downloaded archive has no Makefile (does ref '$REF' exist?)."
fi

# ---------------------------------------------------------------- install
say "installing into $PREFIX"
make -s -C "$DIR" install PREFIX="$PREFIX"
have update-desktop-database && update-desktop-database "$PREFIX/share/applications" >/dev/null 2>&1 || true
have gtk-update-icon-cache && gtk-update-icon-cache -q -t "$PREFIX/share/icons/hicolor" >/dev/null 2>&1 || true

case ":$PATH:" in
  *":$PREFIX/bin:"*) ;;
  *) warn "$PREFIX/bin is not in your PATH. Add this to your shell:  export PATH=\"$PREFIX/bin:\$PATH\"" ;;
esac

printf '\n\033[1;32m/dev/raid installed.\033[0m  Next steps:\n\n'
printf '  gh auth login        # once (repository list, CI and PRs)\n'
printf '  devraid install      # registers hooks and MCP in Claude Code and Codex\n'
printf '  devraid              # opens the app\n\n'
printf 'Documentation: https://kleber-code.github.io/dev-raid/guide.html\n'
printf 'Uninstall:    curl -fsSL https://kleber-code.github.io/dev-raid/install.sh | sh -s -- --uninstall\n'
