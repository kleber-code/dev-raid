#!/bin/sh
# /dev/raid — installer.
#
#   curl -fsSL https://kleber-code.github.io/dev-raid/install.sh | sh
#   wget -qO-  https://kleber-code.github.io/dev-raid/install.sh | sh
#
# Options (environment variables, or arguments after `sh -s --`):
#   DEVRAID_REF=<ref>      commit, tag or branch. Default: main (the app offers updates by comparing commit hashes)
#   DEVRAID_PREFIX=...     where to install. Default: ~/.local (no sudo). E.g.: /usr/local
#   DEVRAID_YES=1          do not ask before installing system dependencies
#   DEVRAID_NO_RESTART=1   do not restart the running app afterwards (the app does that itself, after asking)
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
  rm -f  "$PREFIX/bin/devraid" "$PREFIX/bin/raidpoint" "$PREFIX/share/applications/br.com.satela.DevRaid.desktop" "$PREFIX/share/applications/br.com.satela.DevRaid.Here.desktop" \
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
sha_of() {   # commit hash (40 hex) of a ref on GitHub; empty if it cannot be resolved
  u="https://api.github.com/repos/$REPO/commits/$1"
  if have curl; then curl -fsSL -H "Accept: application/vnd.github.sha" "$u" 2>/dev/null
  elif have wget; then wget -qO- --header="Accept: application/vnd.github.sha" "$u" 2>/dev/null; fi | grep -E '^[0-9a-f]{40}$' | head -n1
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
  SHA=""; if [ -d "$SRC/.git" ] && git -C "$SRC" diff --quiet HEAD 2>/dev/null; then SHA="$(git -C "$SRC" rev-parse HEAD 2>/dev/null || true)"; fi
else
  [ -n "$REF" ] || REF="main"
  # pin the download to an exact commit (immutable: main may move while we install) and remember it for update checks
  SHA="$(sha_of "$REF" || true)"
  say "downloading $REPO @ ${SHA:-$REF}"
  download "https://codeload.github.com/$REPO/tar.gz/${SHA:-$REF}" "$TMP/src.tar.gz"
  tar -xzf "$TMP/src.tar.gz" -C "$TMP"
  DIR="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n1)"
  [ -f "$DIR/Makefile" ] || die "the downloaded archive has no Makefile (does ref '$REF' exist?)."
fi

# ---------------------------------------------------------------- install
say "installing into $PREFIX"
make -s -C "$DIR" install PREFIX="$PREFIX" COMMIT="${SHA:-}"
have update-desktop-database && update-desktop-database "$PREFIX/share/applications" >/dev/null 2>&1 || true
have gtk-update-icon-cache && gtk-update-icon-cache -q -t "$PREFIX/share/icons/hicolor" >/dev/null 2>&1 || true

case ":$PATH:" in
  *":$PREFIX/bin:"*) ;;
  *) warn "$PREFIX/bin is not in your PATH. Add this to your shell:  export PATH=\"$PREFIX/bin:\$PATH\"" ;;
esac

# health check: fixes what an update/migration leaves behind (stale hooks/MCP paths, missing tools) and shows the result
say "health check"
"$PREFIX/bin/raidpoint" doctor --fix || warn "some checks failed (see above); run: raidpoint doctor"
# if the app is open, restart it into the new version (the tmux sessions survive)
if [ "${DEVRAID_NO_RESTART:-0}" != 1 ] && have gapplication && gapplication list-actions br.com.satela.DevRaid 2>/dev/null | grep -qx restart; then
  say "restarting the running app (your sessions stay open)"; gapplication action br.com.satela.DevRaid restart || true
fi

printf '\n\033[1;32m/dev/raid installed.\033[0m  Next steps:\n\n'
printf '  gh auth login        # once (repository list, CI and PRs)\n'
printf '  devraid install      # registers hooks and MCP in Claude Code and Codex\n'
printf '  devraid              # opens the app\n\n'
printf 'Documentation: https://kleber-code.github.io/dev-raid/guide.html\n'
printf 'Uninstall:    curl -fsSL https://kleber-code.github.io/dev-raid/install.sh | sh -s -- --uninstall\n'
