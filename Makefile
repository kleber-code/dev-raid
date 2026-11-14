# /dev/raid — instalação.   make install PREFIX=/usr   |   make install PREFIX=$HOME/.local
PREFIX ?= /usr/local
DESTDIR ?=
LIBDIR  = $(DESTDIR)$(PREFIX)/lib/devraid
BINDIR  = $(DESTDIR)$(PREFIX)/bin
SHAREDIR = $(DESTDIR)$(PREFIX)/share
ICONS = 512 256 128 64 48 32 16

install:
	install -d $(LIBDIR)/bin $(LIBDIR)/raidpoint $(LIBDIR)/config $(BINDIR) $(SHAREDIR)/applications
	install -m755 bin/devraid bin/devraid-gui bin/raidpoint $(LIBDIR)/bin/
	install -m644 raidpoint/*.py $(LIBDIR)/raidpoint/
	install -m644 config/* $(LIBDIR)/config/
	ln -sf ../lib/devraid/bin/devraid   $(BINDIR)/devraid
	ln -sf ../lib/devraid/bin/raidpoint $(BINDIR)/raidpoint
	sed 's|@BIN@|$(PREFIX)/bin|' desktop/br.com.satela.DevRaid.desktop > $(SHAREDIR)/applications/br.com.satela.DevRaid.desktop
	chmod 644 $(SHAREDIR)/applications/br.com.satela.DevRaid.desktop
	for s in $(ICONS); do \
	  install -Dm644 assets/icons/devraid-$$s.png $(SHAREDIR)/icons/hicolor/$${s}x$${s}/apps/devraid.png; done
	install -Dm644 assets/devraid.svg $(SHAREDIR)/icons/hicolor/scalable/apps/devraid.svg
	install -Dm644 assets/br.com.satela.DevRaid.metainfo.xml $(SHAREDIR)/metainfo/br.com.satela.DevRaid.metainfo.xml
	@echo "ok: $(PREFIX)/bin/devraid"

uninstall:
	rm -rf $(LIBDIR)
	rm -f $(BINDIR)/devraid $(BINDIR)/raidpoint $(SHAREDIR)/applications/br.com.satela.DevRaid.desktop
	rm -f $(SHAREDIR)/icons/hicolor/scalable/apps/devraid.svg $(SHAREDIR)/metainfo/br.com.satela.DevRaid.metainfo.xml
	for s in $(ICONS); do rm -f $(SHAREDIR)/icons/hicolor/$${s}x$${s}/apps/devraid.png; done

.PHONY: install uninstall
