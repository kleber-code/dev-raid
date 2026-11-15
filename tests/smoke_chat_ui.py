"""UI smoke test for the chat panel. NOT part of `unittest discover` (needs a display). Run headless with:
    weston --backend=headless --socket=devraid-test &   (then)
    WAYLAND_DISPLAY=devraid-test GDK_BACKEND=wayland python3 tests/smoke_chat_ui.py
"""
import os, sys, tempfile, threading, time
from pathlib import Path
os.environ.setdefault("RAIDPOINT_HOME", tempfile.mkdtemp(prefix="devraid-ui-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib
from raidpoint.chat_ui import ChatPanel, CHAT_CSS
from raidpoint.orchestrator import Provider, ProviderError

class Fake(Provider):
    name = "Fake AI"
    def __init__(self): self.sent, self.decided, self.approvals = [], [], [{"id": "7", "kind": "raid_queue", "tool": "spawn", "summary": "<b>run</b> 2 agents", "origin": "chat", "created": "now"}]
    def send(self, text, on_delta=None):
        self.sent.append(text)
        if text == "boom": raise ProviderError("it broke")
        if text == "stream":
            for d in ("he", "llo"): on_delta(d); time.sleep(0.05)
            return "hello"
        return "echo: " + text
    def history(self, limit=60): return [{"role": "user", "text": "earlier", "ts": 1}, {"role": "assistant", "text": "before", "ts": 2}]
    def pending_approvals(self): return list(self.approvals)
    def decide(self, i, ok): self.decided.append((i, ok)); self.approvals = []

def texts(box):
    out, c = [], box.get_first_child()
    while c: out.append(c.get_label()); c = c.get_next_sibling()
    return out

def pump(cond, secs=5):
    end = time.time() + secs
    while time.time() < end:
        while GLib.MainContext.default().iteration(False): pass
        if cond(): return True
        time.sleep(0.02)
    return False

def check(ok, what):
    print(("ok   " if ok else "FAIL ") + what)
    if not ok: check.failed = True
check.failed = False

fake = Fake()
app = Gtk.Application(application_id="dev.raidpoint.chatsmoke")
def run(app):
    css = Gtk.CssProvider(); css.load_from_string(CHAT_CSS)
    win = Gtk.ApplicationWindow(application=app, default_width=420, default_height=600)
    panel = ChatPanel(lambda: "proj", lambda: {"orchestrator": {"provider": "claude-code"}}, lambda cfg, project: fake)
    win.set_child(panel); win.present(); panel.set_active(True)
    check(pump(lambda: texts(panel.msgs)[:2] == ["earlier", "before"]), "history is shown")
    check(pump(lambda: panel.cards.get_visible()), "pending approval card appears")
    check("FAKE AI" in panel.title.get_label(), "header names the provider")
    panel.entry.get_buffer().set_text("hi"); panel._send()
    check(pump(lambda: texts(panel.msgs)[-2:] == ["hi", "echo: hi"]), "message sent and answered")
    check(pump(lambda: panel.send_btn.get_sensitive()), "input re-enabled after the answer")
    panel.entry.get_buffer().set_text("stream"); panel._send()
    check(pump(lambda: texts(panel.msgs)[-1] == "hello"), "streamed answer assembled")
    check(pump(lambda: panel.send_btn.get_sensitive()), "input re-enabled after the stream")
    panel.entry.get_buffer().set_text("while busy"); panel._set_busy(True); panel._send(); panel._set_busy(False)
    check("while busy" not in fake.sent, "a second message is refused while one is in flight")
    panel.entry.get_buffer().set_text("")
    panel.entry.get_buffer().set_text("boom"); panel._send()
    check(pump(lambda: texts(panel.msgs)[-1] == "it broke"), "provider error shown in the conversation")
    check(pump(lambda: panel.send_btn.get_sensitive()), "input re-enabled after an error")
    n = len(fake.sent); panel.entry.get_buffer().set_text("   "); panel._send(); check(len(fake.sent) == n, "blank message is not sent")
    # approve through the real button
    card = panel.cards.get_first_child(); row = card.get_last_child(); approve = row.get_last_child()
    check(approve.get_label() == "Approve", "card has the Approve button")
    approve.emit("clicked")
    check(pump(lambda: fake.decided == [("7", True)]), "Approve calls decide(id, True)")
    check(pump(lambda: not panel.cards.get_visible()), "card disappears after deciding")
    # third-party text is plain text, never markup
    fake.approvals = [{"id": "8", "kind": "k", "tool": "t", "summary": "<b>run</b>", "origin": "", "created": ""}]
    panel._poll_approvals(); pump(lambda: panel.cards.get_visible())
    summary = panel.cards.get_first_child().get_first_child().get_next_sibling()
    check(summary.get_label() == "<b>run</b>" and not summary.get_use_markup(), "summary shown as plain text")
    panel.set_active(False); check(panel._poll_id is None, "polling stops when hidden")
    app.quit()
app.connect("activate", run)
app.run([])
sys.exit(1 if check.failed else 0)
