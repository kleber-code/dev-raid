# /dev/raid — installation.   make install PREFIX=/usr   |   make install PREFIX=$HOME/.local
PREFIX ?= /usr/local
DESTDIR ?=
LIBDIR  = $(DESTDIR)$(PREFIX)/lib/devraid
BINDIR  = $(DESTDIR)$(PREFIX)/bin
SHAREDIR = $(DESTDIR)$(PREFIX)/share
ICONS = 512 256 128 64 48 32 16
# GitHub commit this install corresponds to (the app compares it with main to offer updates).
# Empty (unknown) when not a clean git checkout: update tracking stays off instead of lying.
COMMIT ?= $(shell git diff --quiet HEAD 2>/dev/null && git rev-parse HEAD 2>/dev/null)

install:
	install -d $(LIBDIR)/bin $(LIBDIR)/raidpoint $(LIBDIR)/config $(BINDIR) $(SHAREDIR)/applications
	install -m755 bin/devraid bin/devraid-gui bin/raidpoint $(LIBDIR)/bin/
	install -m644 raidpoint/*.py $(LIBDIR)/raidpoint/
	install -m644 config/* $(LIBDIR)/config/
	ln -sf ../lib/devraid/bin/devraid   $(BINDIR)/devraid
	ln -sf ../lib/devraid/bin/raidpoint $(BINDIR)/raidpoint
	sed 's|@BIN@|$(PREFIX)/bin|' desktop/br.com.satela.DevRaid.desktop > $(SHAREDIR)/applications/br.com.satela.DevRaid.desktop
	sed 's|@BIN@|$(PREFIX)/bin|' desktop/br.com.satela.DevRaid.Here.desktop > $(SHAREDIR)/applications/br.com.satela.DevRaid.Here.desktop
	chmod 644 $(SHAREDIR)/applications/br.com.satela.DevRaid.desktop $(SHAREDIR)/applications/br.com.satela.DevRaid.Here.desktop
	for s in $(ICONS); do \
	  install -Dm644 assets/icons/devraid-$$s.png $(SHAREDIR)/icons/hicolor/$${s}x$${s}/apps/devraid.png; done
	install -Dm644 assets/devraid.svg $(SHAREDIR)/icons/hicolor/scalable/apps/devraid.svg
	install -Dm644 assets/br.com.satela.DevRaid.metainfo.xml $(SHAREDIR)/metainfo/br.com.satela.DevRaid.metainfo.xml
	@if [ -n "$(COMMIT)" ]; then echo "$(COMMIT)" > $(LIBDIR)/COMMIT; else rm -f $(LIBDIR)/COMMIT; fi
	@echo "ok: $(PREFIX)/bin/devraid"

# server install: the CLI, hooks and MCP only (no GTK app, no desktop files)
install-headless:
	install -d $(LIBDIR)/bin $(LIBDIR)/raidpoint $(LIBDIR)/config $(BINDIR)
	rm -f $(LIBDIR)/bin/devraid-gui
	install -m755 bin/devraid bin/raidpoint $(LIBDIR)/bin/
	install -m644 raidpoint/*.py $(LIBDIR)/raidpoint/
	install -m644 config/* $(LIBDIR)/config/
	ln -sf ../lib/devraid/bin/devraid   $(BINDIR)/devraid
	ln -sf ../lib/devraid/bin/raidpoint $(BINDIR)/raidpoint
	@if [ -n "$(COMMIT)" ]; then echo "$(COMMIT)" > $(LIBDIR)/COMMIT; else rm -f $(LIBDIR)/COMMIT; fi
	@echo "ok: $(PREFIX)/bin/devraid (server install)"

uninstall:
	rm -rf $(LIBDIR)
	rm -f $(BINDIR)/devraid $(BINDIR)/raidpoint $(SHAREDIR)/applications/br.com.satela.DevRaid.desktop $(SHAREDIR)/applications/br.com.satela.DevRaid.Here.desktop
	rm -f $(SHAREDIR)/icons/hicolor/scalable/apps/devraid.svg $(SHAREDIR)/metainfo/br.com.satela.DevRaid.metainfo.xml
	for s in $(ICONS); do rm -f $(SHAREDIR)/icons/hicolor/$${s}x$${s}/apps/devraid.png; done

.PHONY: install install-headless uninstall
