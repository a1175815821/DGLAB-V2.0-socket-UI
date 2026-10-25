from dataclasses import dataclass, field
from typing import Any

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
DEFAULT_WAVE = [(5, 95, 20)]


@dataclass
class AppState:
    client_id: str = ""
    target_id: str | None = None
    limit_a: int = DEFAULT_LIMIT
    limit_b: int = DEFAULT_LIMIT
    strength_a: int = 0
    strength_b: int = 0
    wave_a: list[tuple[int, int, int]] = field(default_factory=lambda: list(DEFAULT_WAVE))
    wave_b: list[tuple[int, int, int]] = field(default_factory=lambda: list(DEFAULT_WAVE))
    wave_convert_ratio: int = 5
    qr_content: str = ""
    debug: bool = False

    device_connected: bool = False
    device_connecting: bool = False
    device_error: str = ""

    ws_connected: bool = False
    ws_bound: bool = False
    ws_url: str = ""
    last_error: str = ""
    logs: list[dict[str, Any]] = field(default_factory=list)

    def clamp_strength(self) -> None:
        self.strength_a = max(0, min(self.strength_a, self.limit_a))
        self.strength_b = max(0, min(self.strength_b, self.limit_b))

    def set_strength(self, channel: str, value: int, mode: str = "set") -> None:
        ch = channel.upper()
        if ch in ("A", "1"):
            self.strength_a = _apply_strength(self.strength_a, self.limit_a, value, mode)
        elif ch in ("B", "2"):
            self.strength_b = _apply_strength(self.strength_b, self.limit_b, value, mode)

    def push_log(self, key: str, params: dict[str, Any] | None = None, limit: int = 80) -> None:
        """Store i18n log entries as {key, params}. Frontend translates by key."""
        entry: dict[str, Any] = {"key": key}
        if params:
            entry["params"] = params
        self.logs.append(entry)
        if len(self.logs) > limit:
            self.logs = self.logs[-limit:]

    def snapshot(self) -> dict[str, Any]:
        return {
            "clientId": self.client_id,
            "targetId": self.target_id,
            "limitA": self.limit_a,
            "limitB": self.limit_b,
            "strengthA": self.strength_a,
            "strengthB": self.strength_b,
            "waveA": self.wave_a,
            "waveB": self.wave_b,
            "waveConvertRatio": self.wave_convert_ratio,
            "qrContent": self.qr_content,
            "debug": self.debug,
            "deviceConnected": self.device_connected,
            "deviceConnecting": self.device_connecting,
            "deviceError": self.device_error,

            "wsConnected": self.ws_connected,
            "wsBound": self.ws_bound,
            "wsUrl": self.ws_url,
            "lastError": self.last_error,
            "logs": self.logs[-30:],
        }


def _apply_strength(current: int, limit: int, value: int, mode: str) -> int:
    if mode == "sub":
        return max(0, current - value)
    if mode == "add":
        return min(limit, current + value)
    return max(0, min(limit, value))


class dglab_message:
    def __init__(self, type_: str, clientId: str, targetId: str, message: str):
        self.type_ = type_
        self.clientId = clientId
        self.targetId = targetId
        self.message = message


# Protocol error codes -> i18n keys (frontend translates)
code = {
    200: ("log.ws_connected", True),
    209: ("error.peer_disconnected", False),
    210: ("error.invalid_client_id", False),
    211: ("error.bind_timeout", False),
    400: ("error.id_already_bound", False),
    401: ("error.target_not_found", False),
    402: ("error.not_bound", False),
    403: ("error.invalid_json", False),
    404: ("error.recipient_offline", False),
    405: ("error.message_too_long", False),
    500: ("error.server_internal", False),
}
