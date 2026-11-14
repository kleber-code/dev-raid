# Releasing a version

1. Bump the version in `bin/devraid` (`VERSION`), `packaging/aur/PKGBUILD` (`pkgver`), `packaging/rpm/devraid.spec`
   (`Version` + `%changelog`) and `assets/br.com.satela.DevRaid.metainfo.xml` (`<release>`). Note it in `CHANGELOG.md`.
2. Commit, tag and release:
   ```bash
   git tag -a v0.2.0 -m "devraid 0.2.0" && git push origin main v0.2.0
   gh release create v0.2.0 --generate-notes
   ```
   From then on the one-line installer picks up this release by default (and existing `curl | sh` installs update to it automatically).
3. **AUR** (requires an aur.archlinux.org account with an SSH key registered):
   ```bash
   git clone ssh://aur@aur.archlinux.org/devraid.git aur-devraid && cd aur-devraid
   cp ../packaging/aur/PKGBUILD .
   updpkgsums                              # fills in the sha256 for tag v0.2.0
   makepkg --printsrcinfo > .SRCINFO
   makepkg -si                             # local test (on Arch)
   git add PKGBUILD .SRCINFO && git commit -m "devraid 0.2.0" && git push
   ```
   For `devraid-git`: same flow, with `packaging/aur/PKGBUILD-git` copied as `PKGBUILD` into a `devraid-git` repository.
4. **RPM / COPR** (Fedora): `rpmbuild -ba packaging/rpm/devraid.spec` (with the tarball in `SOURCES/`) or point a COPR project at the repository.
5. Update the website: `cp install.sh docs/install.sh` and, if the interface changed, retake the screenshots in `docs/img/`.
