Piper TTS Control – Portable Edition

A simple, self-contained, portable graphical interface for Piper TTS
(offline neural text-to-speech system by rhasspy)

https://github.com/rhasspy/piper

This application is intentionally designed to be fully portable:
- Just copy the entire folder anywhere
- Place your voice models (*.onnx + *.onnx.json) in the voices/ subfolder
- Run: python3 main.py
- All settings are saved in config.json inside the same folder
- History, favorites, presets and recents are saved in separate JSON files in the same folder

No installation, no system-wide dependencies beyond Python + GTK4 + audio tools.

Features
--------
• Large text input area
• Voice selection (auto-detected from voices/ folder)
• Audio output device selection (PulseAudio / PipeWire sinks)
• Adjustable parameters:
  - Speech speed (length_scale)
  - Noise scale / noise_w (character / expressiveness)
  - Volume multiplier (via sox when ≠ 1.0)
• Mute button (stops current speech and blocks new playback)
• History: last 10 unique spoken texts (newest first)
• Favorites: persistent starred phrases (add from history, delete individually)
• Stop button (kills ongoing synthesis + playback)

Requirements
------------
Software you need (usually already present on most Linux distributions):

• Linux with PipeWire or PulseAudio
• Python 3.8 or newer
• PyGObject + GTK 4
  Ubuntu/Debian:    sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0
  Fedora:           sudo dnf install python3-gobject gtk4
  Arch:             sudo pacman -S python-gobject gtk4

• piper-tts binary in your $PATH
  (download from https://github.com/rhasspy/piper/releases)

• pactl (comes with pulseaudio-utils or pipewire-pulse)

• pw-play (PipeWire)  or  paplay (PulseAudio fallback)

• sox (strongly recommended for volume control when slider ≠ 1.0)
  sudo apt install sox   /   sudo dnf install sox   /   sudo pacman -S sox

Voice models
------------
Place .onnx and .onnx.json files into the voices/ folder.

Example folder structure:

piper-control-portable/
├── voices/
│   ├── en_US-lessac-medium.onnx
│   ├── en_US-lessac-medium.onnx.json
│   ├── pt_BR-faber-medium.onnx
│   └── pt_BR-faber-medium.onnx.json
├── main.py
├── ui.py
├── engine.py
├── settings.py
├── utils.py
├── config.json           ← created automatically when you change settings
├── history.json          ← created automatically from spoken text
├── favorites.json        ← created automatically from saved favorites
├── presets.json          ← created automatically from saved presets
└── recents.json          ← created automatically from recent selections

Basic usage
-----------
1. Write or paste text in the large text area
2. (Optional) Open "Audio Settings" expander
   • Choose a voice
   • Choose output device (if you have several)
   • Adjust speed / noise / volume sliders
3. Click "Speak"
4. (Optional) After speaking, open "History & Favorites" expander
   • Click ★ on a recent entry to add it to favorites
   • Click "Use" on any entry to reload text
   • In favorites: click "Delete" to remove entries
5. Click "Mute" to silence everything immediately
6. Click "Stop" if the speech is taking too long or is incorrect

Controls explained
------------------
Text area              →  Type or paste what you want to speak
Voice dropdown         →  Selects which model to use (saved)
Output dropdown        →  Selects audio sink (friendly names, saved)
Speed slider           →  0.7 = slower, 1.5 = faster (saved)
Noise slider           →  0.0 = clean, 1.0 = very expressive/noisy (saved)
Volume slider          →  0.0 = silent, 2.0 = very loud (saved, requires sox)
Mute button            →  Red + "Unmute" when active, stops all sound (saved)
Speak                  →  Generate and play the current text
Stop                   →  Immediately kill synthesis + playback
Clear                  →  Empty the text area

History & Favorites panel
-------------------------
Located in the bottom expander.

Recent messages:
• Shows up to 10 most recent unique texts (newest at top)
• "Use" → loads text back into main input area
• "★"   → adds the text to Favorites

Favorites:
• Persistent list (no automatic limit)
• "Use"   → loads text
• "Delete" → removes from favorites

All changes are saved instantly to the local JSON files.

Troubleshooting quick list
--------------------------
No voices shown           → No .onnx files in voices/ folder
No sound                  → Check selected device, mute status, pw-play/paplay working?
Volume slider ineffective → Install sox package
Long device names ugly    → Should be ellipsized (GTK theme issue?)
History/Favorites gone    → history.json, favorites.json, or config.json deleted or corrupted
App won't start           → Missing PyGObject / GTK4 packages

Enjoy your portable TTS control!
kinoko – Nova Friburgo, RJ – 2026
