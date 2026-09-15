import asyncio
import hashlib
import hmac
import os
import socket
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Set

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from vmix.client import vmix_client
from vmix.config import config_manager

# Token Authentication
def generate_token(password: str) -> str:
    cfg = config_manager.get()
    timestamp = str(int(time.time() * 1000))
    secret = cfg.get("authTokenSecret", "secret").encode("utf-8")
    msg = (password + timestamp).encode("utf-8")
    digest = hmac.new(secret, msg, hashlib.sha256).hexdigest()
    return f"{digest}.{timestamp}"

def verify_token(token: Optional[str]) -> bool:
    if not token or "." not in token:
        return False
    cfg = config_manager.get()
    parts = token.split(".")
    if len(parts) != 2:
        return False
    token_hmac, timestamp = parts
    secret = cfg.get("authTokenSecret", "secret").encode("utf-8")
    password = cfg.get("password", "vmix")
    expected_hmac = hmac.new(secret, (password + timestamp).encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(token_hmac, expected_hmac):
        return False

    # Valid for 30 days
    try:
        age_ms = int(time.time() * 1000) - int(timestamp)
        return age_ms < 30 * 24 * 60 * 60 * 1000
    except ValueError:
        return False

def require_auth(authorization: Optional[str] = Header(None), token: Optional[str] = Query(None)) -> bool:
    auth_token = None
    if authorization and authorization.startswith("Bearer "):
        auth_token = authorization[7:]
    elif token:
        auth_token = token

    if not verify_token(auth_token):
        raise HTTPException(status_code=401, detail="Unauthorized: Valid password token required")
    return True

# WebSocket Client Registry
connected_ws_clients: Set[WebSocket] = set()

async def broadcast_state(state: Dict[str, Any]) -> None:
    if not connected_ws_clients:
        return
    payload = {"type": "state", "data": state}
    to_remove = set()
    for ws in list(connected_ws_clients):
        try:
            await ws.send_json(payload)
        except Exception:
            to_remove.add(ws)
    connected_ws_clients.difference_update(to_remove)

# Hook vMix client updates to broadcast
vmix_client.add_callback(broadcast_state)

def _asyncio_reset_guard(loop: asyncio.AbstractEventLoop, context: Dict[str, Any]) -> None:
    # Windows: a phone/tablet/browser dropping its socket makes the proactor raise
    # WinError 10054 inside _call_connection_lost. Harmless, but asyncio prints it.
    exc = context.get("exception")
    if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
        return
    loop.default_exception_handler(context)

def install_asyncio_reset_guard() -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.set_exception_handler(_asyncio_reset_guard)

# App Lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):
    install_asyncio_reset_guard()
    vmix_client.start()
    yield
    vmix_client.stop()

app = FastAPI(title="vMix Web Switcher", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class LoginRequest(BaseModel):
    password: str

class SwitchRequest(BaseModel):
    input: Any
    transition: Optional[str] = None
    duration: Optional[int] = None

class FunctionRequest(BaseModel):
    function: str
    params: Optional[Dict[str, Any]] = None

class OverlayRequest(BaseModel):
    overlay: int
    input: Any

class AudioRequest(BaseModel):
    input: Any

class VolumeRequest(BaseModel):
    input: Any
    volume: float

class IgnoreRequest(BaseModel):
    input: Any
    ignore: Optional[bool] = None

class AliasRequest(BaseModel):
    input: Any
    name: Optional[str] = None
    color: Optional[str] = None

class ConfigUpdateRequest(BaseModel):
    vmixHost: Optional[str] = None
    vmixPort: Optional[int] = None
    defaultTransition: Optional[str] = None
    transitionDuration: Optional[int] = None
    switcherMode: Optional[str] = None
    pollIntervalMs: Optional[int] = None
    previewFps: Optional[float] = None
    livelanUrl: Optional[str] = None
    mockMode: Optional[bool] = None
    newPassword: Optional[str] = None

# Network helper
def get_network_ips(port: int) -> List[str]:
    ips: List[str] = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        primary = s.getsockname()[0]
        s.close()
        ips.append(f"http://{primary}:{port}")
    except Exception:
        pass

    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ":" not in ip and not ip.startswith("127."):
                candidate = f"http://{ip}:{port}"
                if candidate not in ips:
                    ips.append(candidate)
    except Exception:
        pass

    return list(dict.fromkeys(ips))

# Auth Endpoints
@app.post("/api/auth/login")
async def login(req: LoginRequest):
    cfg = config_manager.get()
    if req.password == cfg.get("password", "vmix"):
        token = generate_token(cfg.get("password", "vmix"))
        return {"success": True, "token": token}
    raise HTTPException(status_code=401, detail="Incorrect password")

@app.get("/api/auth/check")
async def check_auth(authorization: Optional[str] = Header(None)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    return {"authenticated": verify_token(token)}

# vMix Controls
@app.get("/api/vmix/state")
async def get_state(_: bool = Depends(require_auth)):
    state = vmix_client.last_state or {
        "connected": vmix_client.connected,
        "lastError": vmix_client.last_error,
        "fadeToBlack": False,
        "inputs": [],
        "visibleInputs": [],
        "allInputs": []
    }
    return state

@app.post("/api/vmix/switch")
async def switch_source(req: SwitchRequest, _: bool = Depends(require_auth)):
    if req.input is None:
        raise HTTPException(status_code=400, detail="Input is required")
    try:
        res = await vmix_client.switch_input(req.input, req.transition, req.duration)
        return {"success": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/vmix/function")
async def execute_function(req: FunctionRequest, _: bool = Depends(require_auth)):
    try:
        res = await vmix_client.execute_function(req.function, req.params or {})
        return {"success": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/vmix/thumbnail/{input_id}")
async def get_thumbnail(input_id: str, _: bool = Depends(require_auth)):
    data, mime = await vmix_client.get_thumbnail(input_id)
    return Response(content=data, media_type=mime, headers={"Cache-Control": "no-store"})

@app.post("/api/vmix/overlay")
async def toggle_overlay(req: OverlayRequest, _: bool = Depends(require_auth)):
    try:
        res = await vmix_client.toggle_overlay(req.overlay, req.input)
        return {"success": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/vmix/audio")
async def toggle_audio(req: AudioRequest, _: bool = Depends(require_auth)):
    try:
        res = await vmix_client.toggle_audio(req.input)
        return {"success": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/vmix/volume")
async def set_volume(req: VolumeRequest, _: bool = Depends(require_auth)):
    try:
        res = await vmix_client.execute_function("SetVolume", {"Input": req.input, "Value": req.volume})
        return {"success": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Source Management (Ignore/Hide inputs)
@app.post("/api/sources/ignore")
async def toggle_ignore(req: IgnoreRequest, _: bool = Depends(require_auth)):
    updated = config_manager.toggle_ignored_input(req.input, req.ignore)
    await vmix_client.poll()
    return {"success": True, "ignoredInputs": updated}

@app.post("/api/sources/unignore-all")
async def unignore_all(_: bool = Depends(require_auth)):
    config_manager.update({"ignoredInputs": []})
    await vmix_client.poll()
    return {"success": True, "ignoredInputs": []}

@app.post("/api/sources/alias")
async def set_alias(req: AliasRequest, _: bool = Depends(require_auth)):
    cfg = config_manager.get()
    aliases = dict(cfg.get("inputAliases", {}))
    colors = dict(cfg.get("inputColors", {}))

    str_input = str(req.input)
    if req.name is not None:
        if req.name.strip():
            aliases[str_input] = req.name.strip()
        else:
            aliases.pop(str_input, None)

    if req.color is not None:
        if req.color:
            colors[str_input] = req.color
        else:
            colors.pop(str_input, None)

    config_manager.update({"inputAliases": aliases, "inputColors": colors})
    await vmix_client.poll()
    return {"success": True, "inputAliases": aliases, "inputColors": colors}

# Config Endpoints
@app.get("/api/config")
async def get_config(_: bool = Depends(require_auth)):
    cfg = config_manager.get()
    cfg.pop("authTokenSecret", None)
    cfg.pop("password", None)
    return cfg

@app.put("/api/config")
async def update_config(req: ConfigUpdateRequest, _: bool = Depends(require_auth)):
    updates: Dict[str, Any] = {}
    if req.vmixHost is not None:
        updates["vmixHost"] = req.vmixHost.strip()
    if req.vmixPort is not None:
        updates["vmixPort"] = int(req.vmixPort)
    if req.defaultTransition is not None:
        updates["defaultTransition"] = req.defaultTransition.strip()
    if req.transitionDuration is not None:
        updates["transitionDuration"] = int(req.transitionDuration)
    if req.switcherMode is not None:
        updates["switcherMode"] = req.switcherMode
    if req.pollIntervalMs is not None:
        updates["pollIntervalMs"] = int(req.pollIntervalMs)
    if req.previewFps is not None:
        updates["previewFps"] = min(10.0, max(0.5, float(req.previewFps)))
    if req.livelanUrl is not None:
        updates["livelanUrl"] = req.livelanUrl.strip()
    if req.mockMode is not None:
        updates["mockMode"] = bool(req.mockMode)
    if req.newPassword and len(req.newPassword.strip()) >= 3:
        updates["password"] = req.newPassword.strip()

    new_cfg = config_manager.update(updates)
    await vmix_client.poll()

    safe_cfg = dict(new_cfg)
    safe_cfg.pop("authTokenSecret", None)
    safe_cfg.pop("password", None)
    return {"success": True, "config": safe_cfg}

@app.get("/api/system/network")
async def network_info(_: bool = Depends(require_auth)):
    port = config_manager.get().get("port", 3000)
    return {"port": port, "ips": get_network_ips(port)}

# WebSocket Endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = Query(None)):
    await websocket.accept()

    # Authenticate token from query param or initial message
    is_authed = verify_token(token)
    if not is_authed:
        try:
            msg = await asyncio.wait_for(websocket.receive_json(), timeout=3.0)
            if msg.get("type") == "auth" and verify_token(msg.get("token")):
                is_authed = True
                await websocket.send_json({"type": "auth_success"})
            else:
                await websocket.send_json({"type": "auth_error", "message": "Invalid token"})
                await websocket.close(code=4001)
                return
        except Exception:
            await websocket.close(code=4001)
            return

    connected_ws_clients.add(websocket)

    # Send current state immediately
    if vmix_client.last_state:
        await websocket.send_json({"type": "state", "data": vmix_client.last_state})

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            if action == "switch":
                await vmix_client.switch_input(data.get("input"), data.get("transition"), data.get("duration"))
            elif action == "function":
                await vmix_client.execute_function(data.get("function"), data.get("params"))
            elif action == "overlay":
                await vmix_client.toggle_overlay(data.get("overlay"), data.get("input"))
            elif action == "audio":
                await vmix_client.toggle_audio(data.get("input"))
            elif action == "volume":
                await vmix_client.execute_function("SetVolume", {"Input": data.get("input"), "Value": data.get("value")})
            elif action == "recording":
                await vmix_client.execute_function("StartStopRecording")
            elif action == "streaming":
                await vmix_client.execute_function("StartStopStreaming")
            elif action == "external":
                await vmix_client.execute_function("StartStopExternal")
            elif action == "ping":
                await websocket.send_json({"type": "pong"})
            elif action == "getState" and vmix_client.last_state:
                await websocket.send_json({"type": "state", "data": vmix_client.last_state})
    except (WebSocketDisconnect, Exception):
        connected_ws_clients.discard(websocket)

# Mount Static Files (Web GUI)
import sys
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    static_dir = os.path.join(sys._MEIPASS, "public")
else:
    static_dir = os.path.join(os.path.dirname(__file__), "public")

if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    import uvicorn
    cfg = config_manager.get()
    port = cfg.get("port", 3000)

    print("\n=============================================================")
    print("     vMix Web Switcher (Python FastAPI) Starting!            ")
    print("=============================================================")
    print(f" Local URL:           http://localhost:{port}")
    ips = get_network_ips(port)
    if ips:
        print(" Network Access (Phones / Tablets / Laptops):")
        for u in ips:
            print(f"   -> {u}")
    print("-------------------------------------------------------------")
    print(f" Default Password:    {cfg.get('password', 'vmix')}")
    print(f" Targeting vMix at:   http://{cfg.get('vmixHost', '127.0.0.1')}:{cfg.get('vmixPort', 8088)}")
    print(f" Default Transition:  {cfg.get('defaultTransition', 'Fade')} ({cfg.get('transitionDuration', 500)}ms)")
    print("=============================================================\n")

    uvicorn.run("server:app", host="0.0.0.0", port=port, log_level="warning")
