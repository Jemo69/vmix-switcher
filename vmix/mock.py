from typing import Any, Dict, List

class MockVMix:
    def __init__(self):
        self.active = 1
        self.preview = 2
        self.recording = False
        self.streaming = False
        self.fullscreen = False
        self.fade_to_black = False
        self.overlays: Dict[str, Any] = {"1": None, "2": None, "3": None, "4": None}

        self.inputs: List[Dict[str, Any]] = [
            {"number": 1, "key": "mock-1", "title": "Camera 1 - Host", "shortTitle": "Host Cam", "type": "Camera", "state": "Running", "muted": False, "volume": 100},
            {"number": 2, "key": "mock-2", "title": "Camera 2 - Guest", "shortTitle": "Guest Cam", "type": "Camera", "state": "Running", "muted": False, "volume": 100},
            {"number": 3, "key": "mock-3", "title": "Camera 3 - Wide Shot", "shortTitle": "Wide Shot", "type": "Camera", "state": "Running", "muted": False, "volume": 100},
            {"number": 4, "key": "mock-4", "title": "Screen Share - PPT", "shortTitle": "Screen PPT", "type": "DesktopCapture", "state": "Running", "muted": True, "volume": 0},
            {"number": 5, "key": "mock-5", "title": "Video Clip - Intro", "shortTitle": "Intro Video", "type": "Video", "state": "Paused", "muted": False, "volume": 100},
            {"number": 6, "key": "mock-6", "title": "Lower Third - Speaker", "shortTitle": "Lower Third", "type": "Title", "state": "Running", "muted": True, "volume": 0},
            {"number": 7, "key": "mock-7", "title": "Microphone Main", "shortTitle": "Mic Main", "type": "Audio", "state": "Running", "muted": False, "volume": 100},
            {"number": 8, "key": "mock-8", "title": "Color Bars / Test Pattern", "shortTitle": "Test Bars", "type": "Colour", "state": "Running", "muted": True, "volume": 0},
        ]

    def get_state(self) -> Dict[str, Any]:
        return {
            "version": "Mock-vMix-26.0",
            "edition": "Simulator (Python)",
            "preset": "Demo_Show_Preset.vmix",
            "active": self.active,
            "preview": self.preview,
            "recording": self.recording,
            "streaming": self.streaming,
            "fullscreen": self.fullscreen,
            "fadeToBlack": self.fade_to_black,
            "overlays": dict(self.overlays),
            "inputs": [
                {
                    **inp,
                    "isActive": int(inp["number"]) == int(self.active),
                    "isPreview": int(inp["number"]) == int(self.preview),
                    "activeOverlays": [int(k) for k, v in self.overlays.items() if v is not None and int(v) == int(inp["number"])]
                }
                for inp in self.inputs
            ]
        }

    def execute_function(self, func_name: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        params = params or {}
        fn = (func_name or "").lower()
        input_num = int(params.get("Input")) if params.get("Input") is not None and str(params.get("Input")).isdigit() else None

        if fn in ("cut", "cutdirect", "activeinput"):
            if input_num:
                self.active = input_num
            else:
                self.active, self.preview = self.preview, self.active
        elif fn in ("fade", "zoom", "wipe", "slide", "fly", "crosszoom", "quickplay") or fn.startswith("transition"):
            if input_num:
                self.preview = self.active
                self.active = input_num
            else:
                self.active, self.preview = self.preview, self.active
        elif fn == "previewinput":
            if input_num:
                self.preview = input_num
        elif fn in ("fadetoblack", "ftb"):
            self.fade_to_black = not self.fade_to_black
        elif fn.startswith("overlayinput"):
            ov_idx = fn.replace("overlayinput", "").strip()
            if ov_idx in self.overlays and input_num:
                if self.overlays[ov_idx] == input_num:
                    self.overlays[ov_idx] = None
                else:
                    self.overlays[ov_idx] = input_num
        elif fn == "audio" and input_num:
            for inp in self.inputs:
                if inp["number"] == input_num:
                    inp["muted"] = not inp.get("muted", False)
                    break
        elif fn in ("startstoprecording", "recording"):
            self.recording = not self.recording
        elif fn in ("startstopstreaming", "streaming"):
            self.streaming = not self.streaming
        elif fn == "fullscreen":
            self.fullscreen = not self.fullscreen

        return {"success": True, "message": f"Mock function {func_name} executed", "state": self.get_state()}

mock_vmix = MockVMix()
