"""GTK4 chat panel for the orchestrator (see docs/orchestrator.md).

Shows the conversation, an input box, and the approvals the AI is waiting for (approve / reject).
Everything the provider returns is third-party text: it is only ever shown as plain text (no markup, no links).
Network and subprocess work runs in threads; the widgets are only touched from the main loop.
"""
import threading
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gdk, Pango
from . import orchestrator
from .orchestrator import ProviderError

# same hex values as the app's base theme, so core.css_for() recolors them with the chosen theme
CHAT_CSS = """
.chat { background: #181825; border-left: 1px solid #11111b; }
.chat-title { color: #6c7086; font-size: 12px; font-weight: bold; letter-spacing: 1.5px; }
.chat-msg { padding: 9px 12px; border-radius: 10px; font-size: 14px; margin: 3px 8px; }
.chat-user { background: #313244; color: #cdd6f4; }
.chat-ai { background: #1e1e2e; color: #cdd6f4; }
.chat-err { background: #1e1e2e; color: #f38ba8; }
.chat-note { color: #6c7086; font-size: 13px; margin: 4px 12px; }
.chat-card { background: #1e1e2e; border: 1px solid #313244; border-radius: 10px; padding: 8px; margin: 4px 8px; }
.chat-card-title { font-size: 14px; font-weight: bold; }
.chat-card-text { font-size: 13px; }
.chat-card button, .chat-input-box button { font-size: 13px; }
textview.chat-input, textview.chat-input text { background-color: #11111b; color: #cdd6f4; font-size: 14px; }
.chat-input-box { margin: 6px 8px 8px 8px; border-radius: 8px; background: #11111b; padding: 4px; }
"""
POLL_SECONDS = 5


class ChatPanel(Gtk.Box):
    def __init__(self, get_project, get_cfg, provider_factory=None):
        # hexpand=False on purpose: children with hexpand=True would make this panel "want" free space even when
        # its revealer is collapsed, leaving an empty strip next to the terminal
        super().__init__(orientation=Gtk.Orientation.VERTICAL, width_request=360, hexpand=False)
        self.add_css_class("chat")
        self.get_project, self.get_cfg = get_project, get_cfg
        self._factory = provider_factory or orchestrator.get_provider
        self._providers, self._loaded = {}, set()
        self._busy, self._active, self._poll_busy, self._poll_id = False, False, False, None

        head = Gtk.Box(spacing=6, margin_start=12, margin_end=6, margin_top=10, margin_bottom=4)
        self.title = Gtk.Label(label="ORCHESTRATOR", xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END)
        self.title.add_css_class("chat-title")
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", has_frame=False, tooltip_text="Reload history and approvals")
        refresh.connect("clicked", lambda *_: self.reload())
        head.append(self.title); head.append(refresh)

        self.cards = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); self.cards.set_visible(False)
        self.note = Gtk.Label(label="", xalign=0, wrap=True); self.note.add_css_class("chat-note"); self.note.set_visible(False)
        self.msgs = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.END)
        self.scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.scroll.set_child(self.msgs)

        self.entry = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, accepts_tab=False, left_margin=6, right_margin=6,
                                  top_margin=4, bottom_margin=4)
        self.entry.add_css_class("chat-input")
        keys = Gtk.EventControllerKey(); keys.connect("key-pressed", self._on_key); self.entry.add_controller(keys)
        esc = Gtk.ScrolledWindow(min_content_height=44, max_content_height=140, propagate_natural_height=True,
                                 hscrollbar_policy=Gtk.PolicyType.NEVER)
        esc.set_child(self.entry)
        self.send_btn = Gtk.Button(label="Send", valign=Gtk.Align.END); self.send_btn.add_css_class("agent")
        self.send_btn.connect("clicked", self._send)
        box = Gtk.Box(spacing=6); box.add_css_class("chat-input-box"); esc.set_hexpand(True)
        box.append(esc); box.append(self.send_btn)

        for w in (head, self.cards, self.note, self.scroll, box): self.append(w)

    # ------------------------------------------------------------ provider handling
    def _cfg(self):
        return self.get_cfg().get("orchestrator", {}) or {}

    def _key(self):
        c = self._cfg(); kind = c.get("provider") or "claude-code"
        return (kind, c.get("url", ""), self.get_project() if kind == "claude-code" else None)

    def _provider(self):
        k = self._key()
        if k not in self._providers:
            self._providers[k] = self._factory(self._cfg(), k[2])
        return self._providers[k]

    def _say(self, text):
        self.note.set_label(text); self.note.set_visible(bool(text))

    # ------------------------------------------------------------ messages
    def _add(self, role, text):
        lbl = Gtk.Label(label=text, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, xalign=0, selectable=True,
                        use_markup=False, halign=Gtk.Align.FILL)
        lbl.add_css_class("chat-msg"); lbl.add_css_class({"user": "chat-user", "ai": "chat-ai", "err": "chat-err"}[role])
        self.msgs.append(lbl); self._to_bottom()
        return lbl

    def _to_bottom(self):
        def go():
            a = self.scroll.get_vadjustment(); a.set_value(a.get_upper() - a.get_page_size()); return False
        GLib.timeout_add(60, go)

    def _clear(self):
        while (c := self.msgs.get_first_child()): self.msgs.remove(c)

    def _set_busy(self, on):
        self._busy = on; self.send_btn.set_sensitive(not on); self.entry.set_editable(not on)

    # ------------------------------------------------------------ lifecycle (called by the app)
    def set_active(self, on):
        """the panel was shown/hidden: poll approvals only while it is visible"""
        self._active = on
        if on:
            self.reload(); self.entry.grab_focus()
            if self._poll_id is None: self._poll_id = GLib.timeout_add_seconds(POLL_SECONDS, self._tick)
        elif self._poll_id is not None:
            GLib.source_remove(self._poll_id); self._poll_id = None

    def on_project_changed(self):
        if self._active: self.reload()

    def _tick(self):
        if not self._active: self._poll_id = None; return False
        self._poll_approvals(); return True

    def reload(self):
        """redraw the conversation of the current provider/project and refresh approvals"""
        self._clear(); self._say(""); self._render_cards([])
        try: prov = self._provider()
        except ProviderError as e:
            self.title.set_label("ORCHESTRATOR"); self._add("err", str(e))
            self._say("Configure [orchestrator] in ~/.raid_point/config.toml (see docs/orchestrator.md)."); return
        self.title.set_label(f"ORCHESTRATOR · {prov.name}".upper())
        key = self._key()
        def work():
            try: hist = prov.history(40)
            except ProviderError as e: hist = []; GLib.idle_add(lambda: (self._say(f"history unavailable: {e}"), False)[1])
            except Exception: hist = []
            GLib.idle_add(self._show_history, key, hist)
        threading.Thread(target=work, daemon=True).start()
        self._poll_approvals()

    def _show_history(self, key, hist):
        if key != self._key(): return False                      # the user switched project/provider meanwhile
        self._clear()
        if not hist:
            self._say(f"Messages go to {self._providers[key].name}. Ask it to plan or launch work.")
        for m in hist: self._add("user" if m["role"] == "user" else "ai", m["text"])
        return False

    # ------------------------------------------------------------ sending
    def _on_key(self, ctl, keyval, code, state):
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and not (state & Gdk.ModifierType.SHIFT_MASK):
            self._send(); return True
        return False

    def _send(self, *_):
        if self._busy: return
        buf = self.entry.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()
        if not text: return
        try: prov = self._provider()
        except ProviderError as e:
            self._add("err", str(e)); return
        buf.set_text(""); self._say("")
        self._add("user", text); lbl = self._add("ai", "…"); self._set_busy(True)
        acc = []
        def on_delta(d):
            acc.append(d); GLib.idle_add(lambda: (lbl.set_label("".join(acc)), self._to_bottom(), False)[2])
        def work():
            try: ans = prov.send(text, on_delta)
            except ProviderError as e: GLib.idle_add(self._failed, lbl, str(e)); return
            except Exception as e: GLib.idle_add(self._failed, lbl, f"unexpected error: {e}"); return
            GLib.idle_add(self._answered, lbl, ans)
        threading.Thread(target=work, daemon=True).start()

    def _answered(self, lbl, ans):
        lbl.set_label(ans or "(empty answer)"); self._set_busy(False); self._to_bottom()
        self._poll_approvals(); self.entry.grab_focus(); return False

    def _failed(self, lbl, msg):
        lbl.set_label(msg); lbl.remove_css_class("chat-ai"); lbl.add_css_class("chat-err")
        self._set_busy(False); self.entry.grab_focus(); return False

    # ------------------------------------------------------------ approvals
    def _poll_approvals(self):
        if self._poll_busy: return
        try: prov = self._provider()
        except ProviderError: return
        self._poll_busy = True; key = self._key()
        def work():
            try: items = prov.pending_approvals(); err = None
            except ProviderError as e: items, err = None, str(e)
            except Exception as e: items, err = None, str(e)
            GLib.idle_add(self._got_approvals, key, items, err)
        threading.Thread(target=work, daemon=True).start()

    def _got_approvals(self, key, items, err):
        self._poll_busy = False
        if key != self._key(): return False
        if items is not None: self._render_cards(items)      # on error keep what is shown; polling retries
        return False

    def _render_cards(self, items):
        while (c := self.cards.get_first_child()): self.cards.remove(c)
        self.cards.set_visible(bool(items))
        for a in items:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4); card.add_css_class("chat-card")
            t = Gtk.Label(label=" · ".join(x for x in (a["kind"], a["tool"]) if x) or "approval", xalign=0, wrap=True)
            t.add_css_class("chat-card-title")
            s = Gtk.Label(label=a["summary"], xalign=0, wrap=True, selectable=True, use_markup=False); s.add_css_class("chat-card-text")
            o = Gtk.Label(label=" · ".join(x for x in (a["origin"], a["created"]) if x), xalign=0); o.add_css_class("chat-note")
            row = Gtk.Box(spacing=6, halign=Gtk.Align.END)
            no, yes = Gtk.Button(label="Reject"), Gtk.Button(label="Approve"); yes.add_css_class("agent")
            for b, ok in ((no, False), (yes, True)): b.connect("clicked", lambda _b, i=a["id"], ok=ok, r=row: self._decide(i, ok, r))
            row.append(no); row.append(yes)
            for w in (t, s, o, row): card.append(w)
            self.cards.append(card)

    def _decide(self, aid, ok, row):
        try: prov = self._provider()
        except ProviderError as e: self._say(str(e)); return
        c = row.get_first_child()
        while c: c.set_sensitive(False); c = c.get_next_sibling()
        def work():
            try: prov.decide(aid, ok); err = None
            except ProviderError as e: err = str(e)
            except Exception as e: err = str(e)
            GLib.idle_add(self._decided, err)
        threading.Thread(target=work, daemon=True).start()

    def _decided(self, err):
        self._say(f"could not decide: {err}" if err else ""); self._poll_approvals(); return False
