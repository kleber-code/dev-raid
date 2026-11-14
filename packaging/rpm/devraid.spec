Name:           devraid
Version:        0.2.0
Release:        1%{?dist}
Summary:        Orchestrate many AI coding agents in persistent terminals
License:        MIT
URL:            https://github.com/kleber-code/dev-raid
Source0:        %{url}/archive/refs/tags/v%{version}.tar.gz#/%{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  make
BuildRequires:  desktop-file-utils
Requires:       python3 >= 3.11
Requires:       python3-gobject
Requires:       gtk4
Requires:       vte291-gtk4
Requires:       tmux
Requires:       gh
Requires:       libsecret
Recommends:     mosh
Recommends:     gnome-keyring

%description
/dev/raid runs Claude Code, Codex, Aider and other AI coding agents side by side:
one persistent terminal workspace per project (tmux), each agent optionally in its
own git worktree, with a diff review window, usage tracking and an MCP server so
agents can orchestrate each other. GTK4 + VTE.

%prep
%autosetup -n dev-raid-%{version}

%build
# nada a compilar (Python puro)

%install
make install DESTDIR=%{buildroot} PREFIX=%{_prefix}

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/br.com.satela.DevRaid.desktop

%files
%license LICENSE
%doc README.md
%{_bindir}/devraid
%{_bindir}/raidpoint
%{_prefix}/lib/devraid/
%{_datadir}/applications/br.com.satela.DevRaid.desktop
%{_datadir}/icons/hicolor/*/apps/devraid.*
%{_datadir}/metainfo/br.com.satela.DevRaid.metainfo.xml

%changelog
* Fri Nov 13 2026 kleber-code <kleber.code@gmail.com> - 0.2.0-1
- Primeira versão empacotada
