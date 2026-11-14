# Publicar uma versão

1. Atualize a versão em `bin/devraid` (`VERSION`), `packaging/aur/PKGBUILD` (`pkgver`), `packaging/rpm/devraid.spec`
   (`Version` + `%changelog`) e `assets/br.com.satela.DevRaid.metainfo.xml` (`<release>`). Anote em `CHANGELOG.md`.
2. Commit, tag e release:
   ```bash
   git tag -a v0.2.0 -m "devraid 0.2.0" && git push origin main v0.2.0
   gh release create v0.2.0 --generate-notes
   ```
   A partir daqui o instalador de uma linha passa a pegar essa release por padrão.
3. **AUR** (precisa de conta no aur.archlinux.org e uma chave SSH cadastrada):
   ```bash
   git clone ssh://aur@aur.archlinux.org/devraid.git aur-devraid && cd aur-devraid
   cp ../packaging/aur/PKGBUILD .
   updpkgsums                              # preenche o sha256 da tag v0.2.0
   makepkg --printsrcinfo > .SRCINFO
   makepkg -si                             # teste local (em Arch)
   git add PKGBUILD .SRCINFO && git commit -m "devraid 0.2.0" && git push
   ```
   Para o `devraid-git`: mesmo fluxo com `packaging/aur/PKGBUILD-git` copiado como `PKGBUILD` num repositório `devraid-git`.
4. **RPM / COPR** (Fedora): `rpmbuild -ba packaging/rpm/devraid.spec` (com o tarball em `SOURCES/`) ou aponte um projeto COPR para o repositório.
5. Atualize o site: `cp install.sh docs/install.sh` e, se mudou a interface, refaça as capturas em `docs/img/`.
