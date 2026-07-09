import json
import logging
import threading
from typing import Optional

import websocket

from handler import bind, break_, error, heartbeat, msg, response, strength_upload
from model import AppState, dglab_message, local_data
from utils import parse_qr_content

logger = logging.getLogger(__name__)


class WSClientService:
    def __init__(self, state: AppState):
        self.state = state
        self.store = local_data(state)
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def connect(self, qr_content: str = "") -> dict:
        raw = (qr_content or self.state.qr_content or "").strip()
        ws_url, client_id = parse_qr_content(raw)
        if not ws_url or not client_id:
            return {"ok": False, "error": "error.invalid_qr"}

        self.disconnect()
        self.state.qr_content = raw
        self.state.ws_url = ws_url
        self.state.client_id = client_id
        self.state.target_id = None
        self.state.ws_bound = False
        self.state.ws_connected = False
        self.state.last_error = ""
        self.state.push_log("log.ws_connecting", {"url": ws_url})

        self._stop.clear()
        self._ws = websocket.WebSocketApp(
            ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._thread = threading.Thread(target=self._run, daemon=True, name="ws-client")
        self._thread.start()
        return {"ok": True, "wsUrl": ws_url, "clientId": client_id}

    def disconnect(self) -> None:
        self._stop.set()
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        self._ws = None
        self.state.ws_connected = False
        self.state.ws_bound = False
        self.state.push_log("log.ws_disconnected")

    def _run(self) -> None:
        assert self._ws is not None
        try:
            self._ws.run_forever(reconnect=5)
        except Exception as e:
            logger.exception("WS run failed")
            self.state.last_error = str(e)
            self.state.push_log("log.ws_error", {"error": str(e)})
        finally:
            self.state.ws_connected = False

    def _on_open(self, ws):
        self.state.ws_connected = True
        self.state.push_log("log.ws_connected")
        logger.info("WS connection opened")

    def _on_close(self, ws, close_status_code, close_msg):
        self.state.ws_connected = False
        self.state.ws_bound = False
        self.state.push_log("log.ws_closed", {"code": close_status_code})
        logger.info("WS connection closed")

    def _on_error(self, ws, err):
        self.state.last_error = str(err)
        self.state.push_log("log.ws_error", {"error": str(err)})
        logger.error(err)

    def _on_message(self, ws, message_raw):
        logger.debug("Received message: %s", message_raw)
        try:
            data = json.loads(message_raw)
            message = dglab_message(
                type_=data.get("type"),
                clientId=data.get("clientId"),
                targetId=data.get("targetId"),
                message=data.get("message"),
            )
        except Exception as e:
            self.state.push_log("log.ws_bad_message", {"error": str(e)})
            return

        if message.type_ == "heartbeat":
            heartbeat(ws, message, self.store)
            return
        if message.type_ == "bind":
            bind(ws, message, self.store)
            strength_upload(
                ws,
                f"strength-0+0+{self.state.limit_b}+{self.state.limit_a}",
                store=self.store,
            )
            return
        if message.type_ == "msg":
            msg(ws, message, self.store)
            strength_upload(
                ws,
                f"strength-{self.state.strength_a}+{self.state.strength_b}+{self.state.limit_b}+{self.state.limit_a}",
                store=self.store,
            )
            response(ws, "feedback-0", self.store)
            return
        if message.type_ == "break":
            break_(ws, message)
            return
        if message.type_ == "error":
            error(ws, message)
            return
