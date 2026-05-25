import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango, Gdk, GLib

import threading
from typing import Dict, Any, List

from engine import PiperEngine
from settings import load_settings, save_settings
from utils import list_voices, list_audio_sinks
from web_control import WebControl


class PiperUI(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="local.piper.control.portable")
        self.settings: Dict[str, Any] = load_settings()
        self.engine = PiperEngine()
        self.tts_thread: threading.Thread | None = None
        self.sink_map: Dict[str, str] = {}

        self.history: List[str] = self.settings.get("history", [])[:10]
        self.favorites: List[str] = self.settings.get("favorites", [])

        self.web_control = WebControl(
            tts_callback=self.remote_speak,
            stop_callback=self.engine.stop
        )
        self.sidebar_visible = False

    def do_activate(self) -> None:
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("Piper TTS Control")
        self.window.set_default_size(820, 680)

        header = Gtk.HeaderBar()
        header.set_show_title_buttons(True)
        self.window.set_titlebar(header)

        title = Gtk.Label()
        title.set_markup("<b>Piper TTS</b>")
        header.set_title_widget(title)

        menu_btn = Gtk.Button(label="⋯")
        menu_btn.connect("clicked", self.toggle_sidebar)
        header.pack_end(menu_btn)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        self.text_view = Gtk.TextView()
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_view.set_editable(True)
        self.text_view.set_cursor_visible(True)
        self.text_view.set_pixels_above_lines(12)
        self.text_view.set_pixels_below_lines(12)
        self.text_view.set_left_margin(16)
        self.text_view.set_right_margin(16)

        scroll.set_child(self.text_view)
        main_box.append(scroll)

        # Bottom Buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.CENTER)
        btn_box.set_margin_top(12)
        btn_box.set_margin_bottom(16)

        speak_btn = Gtk.Button(label="Speak")
        speak_btn.connect("clicked", self.on_speak)

        stop_btn = Gtk.Button(label="Stop")
        stop_btn.connect("clicked", lambda b: self.engine.stop())

        clear_btn = Gtk.Button(label="Clear")
        clear_btn.connect("clicked", lambda b: self.text_view.get_buffer().set_text(""))

        self.mute_btn = Gtk.ToggleButton(label="Mute")
        muted = self.settings.get("mute", False)
        self.mute_btn.set_active(muted)
        self.mute_btn.connect("toggled", self.on_mute_toggled)
        if muted:
            self.mute_btn.set_label("Unmute")
            self.mute_btn.add_css_class("destructive-action")

        btn_box.append(speak_btn)
        btn_box.append(stop_btn)
        btn_box.append(clear_btn)
        btn_box.append(self.mute_btn)

        main_box.append(btn_box)

        # Sidebar
        self.sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.sidebar.set_margin_top(16)
        self.sidebar.set_margin_bottom(16)
        self.sidebar.set_margin_start(12)
        self.sidebar.set_margin_end(16)

        self.voice_combo = self._create_dropdown(list_voices() or ["No voices"], "voice")
        self.sidebar.append(self._labeled_row("Voice", self.voice_combo))

        sinks = list_audio_sinks()
        display_names, self.sink_map = self._build_device_list(sinks)
        self.device_combo = self._create_dropdown(display_names, "output_device")
        self.sidebar.append(self._labeled_row("Output", self.device_combo))

        self.sidebar.append(Gtk.Label(label="Voice Modulation", xalign=0.0))
        self._add_slider(self.sidebar, "Speed", "speed", 0.6, 1.6, 0.05)
        self._add_slider(self.sidebar, "Noise", "noise", 0.0, 1.0, 0.05)
        self._add_slider(self.sidebar, "Clarity", "noise_w", 0.0, 1.0, 0.05)
        self._add_slider(self.sidebar, "Silence", "sentence_silence", 0.0, 2.0, 0.1)

        phone_exp = Gtk.Expander(label="Phone Control", expanded=False)
        phone_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.phone_status_label = Gtk.Label(label="Disabled")
        phone_box.append(self.phone_status_label)

        self.phone_btn = Gtk.ToggleButton(label="Enable Remote Access")
        self.phone_btn.connect("toggled", self.on_phone_toggled)
        phone_box.append(self.phone_btn)
        phone_exp.set_child(phone_box)
        self.sidebar.append(phone_exp)

        self.paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.paned.set_wide_handle(True)
        self.paned.set_position(820)
        self.paned.set_start_child(main_box)
        self.paned.set_end_child(self.sidebar)

        self.window.set_child(self.paned)
        self.window.present()

        # Key handler
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self.on_textview_key_pressed)
        self.text_view.add_controller(key_ctrl)

    def toggle_sidebar(self, button):
        self.sidebar_visible = not self.sidebar_visible
        if self.sidebar_visible:
            self.paned.set_position(520)
        else:
            self.paned.set_position(820)

    def on_phone_toggled(self, button: Gtk.ToggleButton):
        if button.get_active():
            if self.web_control.start():
                button.set_label("Stop Remote")
                self._update_phone_status(True)
            else:
                button.set_active(False)
        else:
            self.web_control.stop()
            button.set_label("Enable Remote Access")
            self._update_phone_status(False)

    def _update_phone_status(self, enabled: bool):
        if enabled:
            ip = self.web_control.get_local_ip()
            self.phone_status_label.set_markup(f'<span color="#00ff88">Active → {ip}:8080</span>')
        else:
            self.phone_status_label.set_text("Disabled")

    def remote_speak(self, text: str):
        if text.strip():
            GLib.idle_add(self._remote_speak_ui, text.strip())

    def _remote_speak_ui(self, text: str):
        self.text_view.get_buffer().set_text(text)
        self.on_speak(None)
        return False

    # ===================== Helpers =====================

    def _labeled_row(self, text: str, widget: Gtk.Widget) -> Gtk.Box:
        box = Gtk.Box(spacing=12)
        lbl = Gtk.Label(label=text, xalign=0.0)
        lbl.set_width_chars(10)
        box.append(lbl)
        box.append(widget)
        widget.set_hexpand(True)
        return box

    def _create_dropdown(self, items: List[str], key: str) -> Gtk.DropDown:
        model = Gtk.StringList()
        for item in items:
            model.append(item)

        dd = Gtk.DropDown(model=model)
        dd.set_factory(self._create_ellipsizing_factory())

        saved = self.settings.get(key)
        if saved in items:
            try:
                dd.set_selected(items.index(saved))
            except ValueError:
                dd.set_selected(0)
        else:
            dd.set_selected(0)

        return dd

    def _create_ellipsizing_factory(self) -> Gtk.SignalListItemFactory:
        factory = Gtk.SignalListItemFactory()

        def setup(_, item):
            lbl = Gtk.Label(xalign=0.0)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            lbl.set_width_chars(32)
            item.set_child(lbl)

        def bind(_, item):
            lbl = item.get_child()
            lbl.set_text(item.get_item().get_string())

        factory.connect("setup", setup)
        factory.connect("bind", bind)
        return factory

    def _build_device_list(self, sinks: List[str]) -> tuple[list[str], dict[str, str]]:
        displays = []
        mapping = {}
        for name in sinks:
            if not name: continue
            display = name
            if name == "default":
                display = "System Default"
            elif "analog-stereo" in name.lower():
                display = "Analog Stereo"
            elif "easyeffects" in name.lower():
                display = "EasyEffects"
            else:
                if '.' in name:
                    display = name.split('.')[-1].replace('_', ' ').replace('-', ' ').title()
                if len(display) > 30:
                    display = display[:27] + "..."
            displays.append(display)
            mapping[display] = name
        return displays, mapping

    def _add_slider(self, parent: Gtk.Box, label: str, key: str, minv: float, maxv: float, step: float):
        row = Gtk.Box(spacing=12)
        lbl = Gtk.Label(label=label, xalign=0.0)
        lbl.set_width_chars(10)
        row.append(lbl)

        val_lbl = Gtk.Label(label=f"{self.settings.get(key, 1.0):.2f}")
        row.append(val_lbl)

        slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, minv, maxv, step)
        slider.set_value(self.settings.get(key, 1.0))
        slider.set_draw_value(False)
        slider.set_hexpand(True)
        row.append(slider)

        parent.append(row)

        def on_change(s, *_):
            v = s.get_value()
            val_lbl.set_text(f"{v:.2f}")
            self.settings[key] = round(v, 3)
            save_settings(self.settings)

        slider.connect("value-changed", on_change)

    def on_speak(self, button=None):
        buf = self.text_view.get_buffer()
        start, end = buf.get_bounds()
        text = buf.get_text(start, end, False).strip()
        if not text:
            return

        pos = self.voice_combo.get_selected()
        voices = list_voices() or ["en_GB-cori-high"]
        voice = voices[pos] if pos < len(voices) else voices[0]
        self.settings["voice"] = voice

        device = "default"
        pos = self.device_combo.get_selected()
        if pos != Gtk.INVALID_LIST_POSITION and self.sink_map:
            display = self.device_combo.get_selected_item().get_string()
            device = self.sink_map.get(display, "default")
        self.settings["output_device"] = device

        save_settings(self.settings)

        if self.tts_thread and self.tts_thread.is_alive():
            return

        self.tts_thread = threading.Thread(
            target=self.engine._run,
            args=(text, self.settings),
            daemon=True
        )
        self.tts_thread.start()

    def on_mute_toggled(self, button: Gtk.ToggleButton):
        muted = button.get_active()
        self.engine.set_mute(muted)
        self.settings["mute"] = muted
        save_settings(self.settings)

        if muted:
            button.set_label("Unmute")
            button.add_css_class("destructive-action")
        else:
            button.set_label("Mute")
            button.remove_css_class("destructive-action")

    def on_textview_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_F1:           # ← F1 to Speak
            self.on_speak(None)
            return True
        return False


def main():
    app = PiperUI()
    app.run()


if __name__ == "__main__":
    main()
