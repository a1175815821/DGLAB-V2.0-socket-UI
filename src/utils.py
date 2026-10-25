from io import BytesIO

from PIL import Image, ImageGrab
from pyzbar.pyzbar import decode

import logging

from model import AppState


def convert_to_waveset(strength: int, freq: int, wave_convert_ratio: int = 5) -> tuple[int, int, int]:
    ms_per_wave = 1000 / max(freq, 1)
    x = int(ms_per_wave / max(wave_convert_ratio, 1))
    y = int(ms_per_wave - x)
    z = int(strength / 5)
    return x, y, z


def dglab_wave_handler(state: AppState, wave: list, channel: str, wave_convert_ratio: int = 5) -> None:
    waveset = []
    for i in wave:
        freq = int(i[0:2], 16)
        strength = int(i[8:10], 16)
        waveset.append(convert_to_waveset(strength, freq, wave_convert_ratio))
    if channel == "A":
        state.wave_a = waveset
    elif channel == "B":
        state.wave_b = waveset


def decode_qr_code(image):
    decoded_objects = decode(image)
    return [obj.data.decode("utf-8") for obj in decoded_objects]


def pick_ws_qr(qrcodes: list[str]) -> str:
    if not qrcodes:
        return ""
    for code in qrcodes:
        if "wss://" in code or "ws://" in code:
            return code
    return qrcodes[0] if qrcodes else ""


def find_qr_code() -> str:
    try:
        qrcodes = decode_qr_code(ImageGrab.grab())
    except Exception as e:
        logging.error(f"QR scan failed: {e}")
        return ""
    return pick_ws_qr(qrcodes)


def decode_qr_from_bytes(data: bytes) -> str:
    try:
        image = Image.open(BytesIO(data))
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        return pick_ws_qr(decode_qr_code(image))
    except Exception as e:
        logging.error(f"QR image decode failed: {e}")
        return ""


def parse_qr_content(qr_raw: str) -> tuple[str, str]:
    """Return (ws_url, client_id) from DGLAB QR content."""
    qr_raw = (qr_raw or "").strip()
    if not qr_raw:
        return "", ""

    marker = "#DGLAB-SOCKET#"
    if marker in qr_raw:
        ws_url = qr_raw.split(marker, 1)[1]
        client_id = ws_url.rsplit("/", 1)[-1]
        return ws_url, client_id

    if qr_raw.startswith("ws://") or qr_raw.startswith("wss://"):
        client_id = qr_raw.rsplit("/", 1)[-1]
        return qr_raw, client_id

    return "", ""
