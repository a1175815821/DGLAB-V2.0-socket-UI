from __future__ import annotations

import logging
from pathlib import Path

import yaml
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from device import DeviceService
from model import AppState
from utils import decode_qr_from_bytes, find_qr_code
from ws_client import WSClientService

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "web"
CONFIG_PATH = ROOT / "config.yaml"

logging.basicConfig(
    level=logging.INFO,
    format="%(module)s [%(levelname)s]: %(message)s",
)
logger = logging.getLogger("api")

state = AppState()
device_service = DeviceService(state)
ws_service = WSClientService(state)


def load_config() -> None:
    if not CONFIG_PATH.exists():
        return
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    state.qr_content = str(cfg.get("QR_Content") or "")
    state.limit_a = int(cfg.get("Channel_A_limit", 50))
    state.limit_b = int(cfg.get("Channel_B_limit", 50))
    state.wave_convert_ratio = int(cfg.get("Wave_convert_ratio", 5))
    state.debug = bool(cfg.get("Debug", False))
    if state.debug:
        logging.getLogger().setLevel(logging.DEBUG)


def save_config() -> None:
    data = {
        "QR_Content": state.qr_content,
        "Channel_A_limit": state.limit_a,
        "Channel_B_limit": state.limit_b,
        "Wave_convert_ratio": state.wave_convert_ratio,
        "Debug": state.debug,
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


load_config()

app = FastAPI(title="DGLAB V2 Control", version="2.0")


class StrengthBody(BaseModel):
    channel: str = Field(..., description="A or B")
    value: int
    mode: str = Field("set", description="set | add | sub")


class LimitsBody(BaseModel):
    limitA: int | None = None
    limitB: int | None = None


class ConnectBody(BaseModel):
    qrContent: str = ""


class ConfigBody(BaseModel):
    qrContent: str | None = None
    limitA: int | None = None
    limitB: int | None = None
    waveConvertRatio: int | None = None
    debug: bool | None = None


class WaveBody(BaseModel):
    channel: str
    wave: list[list[int]]


@app.on_event("startup")
def on_startup():
    state.push_log("log.api_started")


@app.on_event("shutdown")
def on_shutdown():
    ws_service.disconnect()
    device_service.stop()


@app.get("/api/status")
def get_status():
    return state.snapshot()


@app.post("/api/device/connect")
def device_connect():
    result = device_service.start()
    if result.get("already"):
        state.push_log("log.device_already")
    return state.snapshot()


@app.post("/api/device/disconnect")
def device_disconnect():
    # Zero local strengths immediately so UI/waveform reflect disconnect
    state.strength_a = 0
    state.strength_b = 0
    device_service.stop()
    state.push_log("log.device_disconnected")
    return state.snapshot()



@app.post("/api/strength")
def set_strength(body: StrengthBody):
    ch = body.channel.upper()
    if ch not in ("A", "B", "1", "2"):
        raise HTTPException(400, "error.channel")
    mode = body.mode if body.mode in ("set", "add", "sub") else "set"
    state.set_strength(ch, int(body.value), mode)
    ch_name = ch if ch in ("A", "B") else ("A" if ch == "1" else "B")
    state.push_log(
        "log.strength",
        {
            "channel": ch_name,
            "mode": mode,
            "value": body.value,
            "strengthA": state.strength_a,
            "strengthB": state.strength_b,
        },
    )
    return state.snapshot()


@app.post("/api/limits")
def set_limits(body: LimitsBody):
    if body.limitA is not None:
        state.limit_a = max(0, min(200, int(body.limitA)))
    if body.limitB is not None:
        state.limit_b = max(0, min(200, int(body.limitB)))
    state.clamp_strength()
    save_config()
    state.push_log("log.limits_set", {"limitA": state.limit_a, "limitB": state.limit_b})
    return state.snapshot()


@app.post("/api/wave")
def set_wave(body: WaveBody):
    ch = body.channel.upper()
    waves = [tuple(int(x) for x in item[:3]) for item in body.wave]
    if not waves:
        waves = [(5, 95, 20)]
    if ch in ("A", "1"):
        state.wave_a = waves
        ch_name = "A"
    elif ch in ("B", "2"):
        state.wave_b = waves
        ch_name = "B"
    else:
        raise HTTPException(400, "error.channel")
    state.push_log("log.wave_updated", {"channel": ch_name, "count": len(waves)})
    return state.snapshot()


@app.post("/api/emergency-stop")
def emergency_stop():
    state.strength_a = 0
    state.strength_b = 0
    state.wave_a = [(5, 95, 20)]
    state.wave_b = [(5, 95, 20)]
    state.push_log("log.emergency_stop")
    return state.snapshot()


@app.post("/api/ws/connect")
def ws_connect(body: ConnectBody):
    result = ws_service.connect(body.qrContent or state.qr_content)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "error.connect_failed"))
    save_config()
    return {**result, "status": state.snapshot()}


@app.post("/api/ws/disconnect")
def ws_disconnect():
    ws_service.disconnect()
    return state.snapshot()


@app.post("/api/qr/scan")
def qr_scan():
    code = find_qr_code()
    if not code:
        raise HTTPException(404, "error.no_qr")
    state.qr_content = code
    state.push_log("log.qr_scanned")
    return {"qrContent": code, "status": state.snapshot()}


@app.post("/api/qr/image")
async def qr_image(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "error.no_qr_image")
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(400, "error.image_too_large")
    code = decode_qr_from_bytes(data)
    if not code:
        raise HTTPException(404, "error.no_qr_image")
    state.qr_content = code
    state.push_log("log.qr_from_image")
    return {"qrContent": code, "status": state.snapshot()}


@app.get("/api/config")
def get_config():
    return {
        "qrContent": state.qr_content,
        "limitA": state.limit_a,
        "limitB": state.limit_b,
        "waveConvertRatio": state.wave_convert_ratio,
        "debug": state.debug,
    }


@app.post("/api/config")
def update_config(body: ConfigBody):
    if body.qrContent is not None:
        state.qr_content = body.qrContent
    if body.limitA is not None:
        state.limit_a = max(0, min(200, int(body.limitA)))
    if body.limitB is not None:
        state.limit_b = max(0, min(200, int(body.limitB)))
    if body.waveConvertRatio is not None:
        state.wave_convert_ratio = max(1, int(body.waveConvertRatio))
    if body.debug is not None:
        state.debug = bool(body.debug)
        logging.getLogger().setLevel(logging.DEBUG if state.debug else logging.INFO)
    state.clamp_strength()
    save_config()
    state.push_log("log.config_saved")
    return state.snapshot()


@app.get("/")
def index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(404, "error.frontend_missing")
    return FileResponse(index_path)


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
