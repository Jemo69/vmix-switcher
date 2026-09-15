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
    "previewFps": 4,           # Priority-tier pull rate in fps (0.5 - 60). Drives how
                               # often priority tiles re-poll (cheap 304s) and how eagerly
                               # their snapshots re-render (bounded by vMix render speed).
    "backgroundFps": 1.5,      # Eco-tier pull + render rate in fps (0.1 - 5) for the rest.
    "priorityInputs": [],      # Picked inputs (numbers or keys) on the fast tier.
    "maxPriorityInputs": 20,   # Cap for the priority list. Churches with bigger walls
                               # raise it; small setups lower it to protect Wi-Fi/vMix.
    "livelanUrl": "",          # Optional explicit LiveLAN video URL (http://vMix-IP:8088/livelan).
                               # Empty = auto-derive per device from the page host + vmixPort.
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

    def max_priority_inputs(self) -> int:
        """Configurable priority cap (1-50) so each venue sizes its fast tier."""
        try:
            cap = int(self.config.get("maxPriorityInputs", 20))
        except (TypeError, ValueError):
            cap = 20
        return min(50, max(1, cap))

    def toggle_priority_input(self, input_id: Any, want_priority: bool | None = None) -> List[str]:
        """Pick/unpick a priority input. Adding past the cap raises ValueError."""
        str_id = str(input_id)
        current = [str(x) for x in self.config.get("priorityInputs", [])]

        if want_priority is None:
            want_priority = str_id not in current
        if want_priority:
            if str_id not in current:
                cap = self.max_priority_inputs()
                if len(current) >= cap:
                    raise ValueError(f"Priority list is full ({cap} max) — unpick one first or raise the limit in Settings")
                current.append(str_id)
        else:
            current = [x for x in current if x != str_id]

        def sort_key(x: str):
            return (0, int(x)) if x.isdigit() else (1, x)
        self.config["priorityInputs"] = sorted(current, key=sort_key)
        self.save()
        return self.config["priorityInputs"]

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
