#!/usr/bin/env python3
"""
=============================================================================
CYBERDECK CALENDAR // STANDALONE HUD RUNNER (calendar_hud.py)
=============================================================================
Dedicated floating cyber-glass desktop calendar HUD for the Cyberdeck ecosystem.
Integrates Aura CRM & Aura TPRM non-overlapping streams with RFC 5545 Proton
Calendar export, dual-layer glance privacy, and Work_Hub tray controls.

Architecture:
  - GTK3 + WebKit2 with RGBA transparency compositing (matching Hana Hub)
  - Drag-to-move header & geometry memory in ~/.config/cyberdeck/calendar_geometry.json
  - Single-instance UNIX domain socket listener for instant hotkey/tray toggles
=============================================================================
"""

import os
import sys
import time
import json
import socket
import select
import threading
import subprocess
import signal
from pathlib import Path

# Enforce X11 backend for transparent compositing on GNOME Wayland
os.environ["GDK_BACKEND"] = "x11"

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gtk, Gdk, WebKit2, GLib, Gio

# Project Paths
PROJECT_DIR = Path(__file__).resolve().parent
STATIC_DIR = PROJECT_DIR / "static"
INDEX_HTML = STATIC_DIR / "index.html"
CONFIG_DIR = Path.home() / ".config/cyberdeck"
GEOMETRY_FILE = CONFIG_DIR / "calendar_geometry.json"
SOCKET_PATH = "/tmp/cyberdeck_calendar.sock"

# Bridge & Export imports
sys.path.insert(0, str(PROJECT_DIR))
import calendar_bridge
import export_ics


class CalendarHUDWindow(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_title("Cyberdeck // Calendar HUD")
        self.set_wmclass("cyberdeck-calendar", "CyberdeckCalendar")
        self.set_role("calendar-hud")
        self.set_decorated(False)
        self.set_skip_taskbar_hint(False)
        self.set_app_paintable(True)

        # Enable RGBA Transparency
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)

        # CSS to eliminate any window frame borders
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            window, .background {
                background-color: rgba(0, 0, 0, 0);
                background: transparent;
                box-shadow: none;
                border: none;
            }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            screen,
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Default size and position
        self.set_default_size(940, 640)
        self.set_size_request(680, 480)
        self.set_resizable(True)
        self.load_geometry()

        # WebKit Context & Settings
        web_context = WebKit2.WebContext.get_default()
        web_context.set_cache_model(WebKit2.CacheModel.DOCUMENT_VIEWER)

        settings = WebKit2.Settings()
        settings.set_enable_javascript(True)
        settings.set_enable_developer_extras(False)
        settings.set_allow_file_access_from_file_urls(True)
        settings.set_allow_universal_access_from_file_urls(True)

        content_manager = WebKit2.UserContentManager()
        content_manager.connect("script-message-received::cyberdeckCalendar", self.on_js_message)
        content_manager.register_script_message_handler("cyberdeckCalendar")

        self.webview = WebKit2.WebView.new_with_user_content_manager(content_manager)
        self.webview.set_settings(settings)
        self.webview.set_background_color(Gdk.RGBA(0, 0, 0, 0))

        self.add(self.webview)
        self.webview.load_uri(INDEX_HTML.as_uri())

        # Window event bindings
        self.connect("delete-event", self.on_delete_event)
        self.connect("configure-event", self.on_configure_event)

        # Window dragging state
        self._dragging = False
        self._drag_start_x = 0
        self._drag_start_y = 0

        # Enable dragging from title bar
        self.webview.connect("button-press-event", self.on_button_press)

    def load_geometry(self):
        """Restores saved window geometry."""
        if GEOMETRY_FILE.exists():
            try:
                with open(GEOMETRY_FILE, "r", encoding="utf-8") as f:
                    geom = json.load(f)
                    w = geom.get("width", 940)
                    h = geom.get("height", 640)
                    x = geom.get("x")
                    y = geom.get("y")
                    self.resize(w, h)
                    if x is not None and y is not None:
                        self.move(x, y)
                    return
            except Exception:
                pass
        self.set_position(Gtk.WindowPosition.CENTER)

    def save_geometry(self):
        """Saves current window geometry."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            x, y = self.get_position()
            w, h = self.get_size()
            with open(GEOMETRY_FILE, "w", encoding="utf-8") as f:
                json.dump({"x": x, "y": y, "width": w, "height": h}, f, indent=2)
        except Exception:
            pass

    def on_configure_event(self, widget, event):
        self.save_geometry()
        return False

    def on_delete_event(self, widget, event):
        self.save_geometry()
        self.hide()
        return True  # Hide instead of destroy to allow fast toggling

    def on_button_press(self, widget, event):
        # Allow dragging window when clicking top 44px
        if event.button == 1 and event.y <= 44:
            self.begin_move_drag(event.button, int(event.x_root), int(event.y_root), event.time)
            return True
        return False

    def on_js_message(self, content_manager, js_result):
        """Dispatches incoming IPC messages from JavaScript WebKit."""
        try:
            payload = json.loads(js_result.get_js_value().to_string())
            action = payload.get("action")

            if action == "fetch_events":
                glance = payload.get("glance_mode", False)
                data = calendar_bridge.get_all_calendar_events(glance_mode=glance)
                self.send_js("onEventsLoaded", data)

            elif action == "export_ics":
                stream = payload.get("stream", "all")
                glance = payload.get("glance_only", False)
                res = export_ics.export_calendar(stream=stream, glance_only=glance)
                if res.get("ok"):
                    self.notify_user("Calendar Exported", f"Successfully exported {res['count']} events to {res['path']}")

            elif action == "export_single_ics":
                ev = payload.get("event")
                if ev:
                    res = export_ics.export_calendar(stream=ev.get("source", "all"), glance_only=False)
                    self.notify_user("Event Exported", f"Exported {ev.get('full_title', 'Event')} to {res['path']}")

            elif action == "launch_crm":
                crm_bin = Path.home() / ".local/bin/aura-crm"
                cmd = [str(crm_bin)] if crm_bin.exists() else ["python3", str(Path.home() / "Projects/aura-sync/aura_gui.py")]
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

            elif action == "launch_tprm":
                tprm_bin = Path.home() / ".local/bin/aura-tprm"
                cmd = [str(tprm_bin)] if tprm_bin.exists() else ["python3", str(Path.home() / "Projects/aura-tprm/tprm_gui.py")]
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

            elif action == "add_ops_event":
                new_ev = {
                    "title": payload.get("title"),
                    "start": payload.get("start"),
                    "end": payload.get("end"),
                    "notes": payload.get("notes"),
                    "category": payload.get("category", "task"),
                    "badge": "[● OPS // TASK]"
                }
                calendar_bridge.add_local_ops_event(new_ev)

            elif action == "delete_ops_event":
                calendar_bridge.delete_local_ops_event(payload.get("id"))

            elif action == "minimize":
                self.iconify()

            elif action == "close":
                self.save_geometry()
                self.hide()

        except Exception as e:
            print(f"[Calendar IPC Error] {e}", file=sys.stderr)

    def send_js(self, func_name, data):
        """Sends data payload back into WebKit JS."""
        json_str = json.dumps(data).replace("'", "\\'").replace("\\n", "\\\\n")
        script = f"{func_name}(JSON.parse('{json_str}'));"
        GLib.idle_add(self.webview.evaluate_javascript, script, -1, None, None, None, None, None)

    def notify_user(self, title, message):
        """Displays desktop notification."""
        try:
            subprocess.Popen(["notify-send", "-a", "Cyberdeck Calendar", "-i", str(PROJECT_DIR / "assets/calendar.svg"), title, message])
        except Exception:
            pass


class IPCServer(threading.Thread):
    """UNIX Domain Socket listener for single-instance control (--toggle, --show, --hide)."""
    def __init__(self, window):
        super().__init__(daemon=True)
        self.window = window

    def run(self):
        if os.path.exists(SOCKET_PATH):
            try:
                os.unlink(SOCKET_PATH)
            except OSError:
                pass

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(SOCKET_PATH)
        server.listen(5)
        os.chmod(SOCKET_PATH, 0o600)

        while True:
            try:
                conn, _ = server.accept()
                data = conn.recv(1024).decode("utf-8").strip()
                if data == "toggle":
                    GLib.idle_add(self.handle_toggle)
                elif data == "show":
                    GLib.idle_add(self.handle_show)
                elif data == "hide":
                    GLib.idle_add(self.handle_hide)
                elif data == "quit":
                    GLib.idle_add(Gtk.main_quit)
                conn.sendall(b"OK\n")
                conn.close()
            except Exception:
                break

    def handle_toggle(self):
        if self.window.is_visible():
            self.window.hide()
        else:
            self.window.present()

    def handle_show(self):
        self.window.present()

    def handle_hide(self):
        self.window.hide()


def send_ipc_command(cmd: str) -> bool:
    """Attempts to send command to running instance."""
    if not os.path.exists(SOCKET_PATH):
        return False
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(SOCKET_PATH)
        client.sendall(cmd.encode("utf-8"))
        res = client.recv(1024)
        client.close()
        return True
    except Exception:
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Cyberdeck // Calendar HUD")
    parser.add_argument("--toggle", action="store_true", help="Toggle HUD visibility")
    parser.add_argument("--show", action="store_true", help="Show HUD and bring to front")
    parser.add_argument("--hide", action="store_true", help="Hide HUD")
    parser.add_argument("--quit", action="store_true", help="Quit running HUD instance")
    parser.add_argument("--export-ics", action="store_true", help="Export calendar to .ics file and exit")
    args = parser.parse_args()

    # CLI non-interactive export option
    if args.export_ics:
        res = export_ics.export_calendar()
        print(f"Exported {res['count']} events to: {res['path']}")
        return

    # Check for existing running instance
    if args.toggle:
        if send_ipc_command("toggle"):
            return
    elif args.show:
        if send_ipc_command("show"):
            return
    elif args.hide:
        if send_ipc_command("hide"):
            return
    elif args.quit:
        if send_ipc_command("quit"):
            print("Cyberdeck Calendar HUD terminated.")
            return

    # If socket command failed or no args, launch window
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    win = CalendarHUDWindow()
    ipc_server = IPCServer(win)
    ipc_server.start()

    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
