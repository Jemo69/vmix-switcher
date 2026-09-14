import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any, Dict, List

if getattr(sys, "frozen", False):
    CONFIG_FILE = Path(sys.executable).resolve().parent / "config.json"
else:
    CONFIG_FILE = Path(__file__).resolve().parent.parent / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "port": 3000,
    "password": "vmix",
    "vmixHost": "127.0.0.1",
    "vmixPort": 8088,
    "defaultTransition": "Fade",
    "transitionDuration": 500,
    "switcherMode": "direct",  # 'direct' or 'preview_take'
    "ignoredInputs": [],       # App-side ignored inputs
    "inputAliases": {},        # Friendly nicknames { "1": "Cam 1" }
    "inputColors": {},
    "pollIntervalMs": 300,
    "previewFps": 4,           # Live preview snapshot refresh rate (0.5 - 10)
    "mockMode": False,
    "authTokenSecret": secrets.token_hex(24)
}

class ConfigManager:
    def __init__(self):
        self.config: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self.load()

    def load(self) -> None:
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.config = {**DEFAULT_CONFIG, **data}
            else:
                self.save()
        except Exception as e:
            print(f"[ConfigManager] Error reading config.json ({e}), using defaults")
            self.config = dict(DEFAULT_CONFIG)

    def save(self) -> None:
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"[ConfigManager] Error writing config.json: {e}")

    def get(self) -> Dict[str, Any]:
        return dict(self.config)

    def update(self, new_fields: Dict[str, Any]) -> Dict[str, Any]:
        self.config.update(new_fields)
        self.save()
        return self.get()

    def toggle_ignored_input(self, input_id: Any, should_ignore: bool | None = None) -> List[str]:
        str_id = str(input_id)
        current = set(str(x) for x in self.config.get("ignoredInputs", []))

        if should_ignore is None:
            if str_id in current:
                current.remove(str_id)
            else:
                current.add(str_id)
        elif should_ignore:
            current.add(str_id)
        else:
            current.discard(str_id)

        self.config["ignoredInputs"] = sorted(list(current), key=lambda x: int(x) if x.isdigit() else x)
        self.save()
        return self.config["ignoredInputs"]

config_manager = ConfigManager()
