import json
import logging
import threading
from typing import Optional

import websocket

from handler import bind, error, heartbeat, msg, strength_upload
from model import AppState, dglab_message
from utils import parse_qr_content

logger = logging.getLogger(__name__)


class WSClientService:
    def __init__(self, state: AppState):
        self.state = state
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None

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

        app = websocket.WebSocketApp(
            ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._ws = app
        self._thread = threading.Thread(
            target=self._run, args=(app,), daemon=True, name="ws-client"
        )
        self._thread.start()
        return {"ok": True, "wsUrl": ws_url, "clientId": client_id}

    def disconnect(self) -> None:
        app = self._ws
        self._ws = None
        if app is not None:
            try:
                app.close()
            except Exception:
                pass
        was_active = self.state.ws_connected or self.state.ws_bound
        self.state.ws_connected = False
        self.state.ws_bound = False
        if was_active:
            self.state.push_log("log.ws_disconnected")

    def send_strength_feedback(self) -> None:
        """Push current strengths/limits to the app (order: A+B+limitA+limitB)."""
        state = self.state
        ws = self._ws
        if not state.ws_connected or ws is None:
            return
        payload = (
            f"strength-{state.strength_a}+{state.strength_b}"
            f"+{state.limit_a}+{state.limit_b}"
        )
        try:
            strength_upload(ws, payload, state)
        except Exception as e:
            logger.debug("Strength feedback failed: %s", e)

    def _run(self, app: websocket.WebSocketApp) -> None:
        try:
            app.run_forever(reconnect=5)
        except Exception as e:
            logger.exception("WS run failed")
            if app is self._ws:
                self.state.last_error = str(e)
                self.state.push_log("log.ws_error", {"error": str(e)})
        finally:
            if app is self._ws:
                self.state.ws_connected = False

    def _on_open(self, ws):
        if ws is not self._ws:
            return
        self.state.ws_connected = True
        self.state.push_log("log.ws_connected")
        logger.info("WS connection opened")

    def _on_close(self, ws, close_status_code, close_msg):
        if ws is not self._ws:
            return
        self.state.ws_connected = False
        self.state.ws_bound = False
        self.state.push_log("log.ws_closed", {"code": close_status_code})
        logger.info("WS connection closed")

    def _on_error(self, ws, err):
        if ws is not self._ws:
            return
        self.state.last_error = str(err)
        self.state.push_log("log.ws_error", {"error": str(err)})
        logger.error(err)

    def _on_message(self, ws, message_raw):
        if ws is not self._ws:
            return
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

        try:
            if message.type_ == "heartbeat":
                heartbeat(ws, message, self.state)
            elif message.type_ == "bind":
                bind(ws, message, self.state)
                if self.state.ws_bound:
                    self.send_strength_feedback()
            elif message.type_ == "msg":
                changed = msg(ws, message, self.state)
                if changed:
                    self.send_strength_feedback()
            elif message.type_ == "break":
                # Peer unbound; keep the socket and wait for a new bind.
                if self.state.ws_bound or self.state.target_id:
                    self.state.ws_bound = False
                    self.state.target_id = None
                    self.state.push_log("log.peer_broken")
            elif message.type_ == "error":
                error(ws, message, self.state)
        except Exception as e:
            # A single malformed message must not tear down the connection.
            logger.exception("WS message handler failed")
            self.state.push_log("log.ws_handler_error", {"error": str(e)})
