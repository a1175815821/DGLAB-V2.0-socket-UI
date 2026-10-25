import json
import logging

from model import DEFAULT_WAVE, AppState, code, dglab_message
from utils import dglab_wave_handler

logger = logging.getLogger(__name__)


def bind(client, message: dglab_message, state: AppState) -> None:
    if message.message == "targetId":
        logger.debug("Bind received")
        state.target_id = message.clientId
        client.send(json.dumps({
            "type": "bind",
            "clientId": state.client_id,
            "targetId": state.target_id,
            "message": "DGLAB",
        }))
    elif message.message == "200":
        logger.info("Bind to remote success")
        state.ws_bound = True
        state.push_log("log.ws_bound")
    elif str(message.message).isdigit() and int(message.message) in code:
        err_key = code[int(message.message)][0]
        logger.error("Bind error: %s", err_key)
        state.last_error = err_key
        state.push_log("log.bind_error", {"error": err_key})


def heartbeat(client, message: dglab_message, state: AppState) -> None:
    try:
        code_value = int(message.message)
    except (TypeError, ValueError):
        logger.warning("Unknown heartbeat message: %s", message.message)
        return
    if code_value == 200:
        logger.debug("Heartbeating...")
        client.send(json.dumps({
            "type": "heartbeat",
            "clientId": state.client_id,
            "targetId": state.target_id,
            "message": 200,
        }))
        return
    if code_value in code:
        err_key = code[code_value][0]
        logger.error("Heartbeat error: %s", err_key)
        state.last_error = err_key
        return
    logger.warning("Unknown heartbeat message: %s", message.message)


def msg(client, message: dglab_message, state: AppState) -> bool:
    """Handle one app message.

    Returns True when channel state may have changed, so the caller can push a
    strength feedback back to the app.
    """
    parts = str(message.message).split("-", 1)
    if len(parts) < 2:
        return False
    message_type, message_content = parts
    if message_type == "strength":
        _strength(message_content, state)
        return True
    if message_type == "pulse":
        _pulse(message_content, state)
        return False
    if message_type == "clear":
        _clear(message_content, state)
        return True
    if message_type == "feedback":
        state.push_log("log.app_feedback", {"code": message_content})
    return False


def strength_upload(client, message: str, state: AppState) -> None:
    client.send(json.dumps({
        "type": "msg",
        "clientId": state.client_id,
        "targetId": state.target_id,
        "message": message,
    }))


def error(client, message: dglab_message, state: AppState) -> None:
    raw = str(message.message)
    if raw.isdigit() and int(raw) in code:
        raw = code[int(raw)][0]
    state.last_error = raw
    state.push_log("log.ws_error", {"error": raw})


def _strength(message: str, state: AppState) -> None:
    raw = message.split("+")
    if len(raw) >= 4:
        # App-side sync: strength-A强度+B强度+A上限+B上限
        state.limit_a = max(0, min(200, int(raw[2])))
        state.limit_b = max(0, min(200, int(raw[3])))
        state.strength_a = max(0, min(int(raw[0]), state.limit_a))
        state.strength_b = max(0, min(int(raw[1]), state.limit_b))
        state.push_log(
            "log.app_sync",
            {
                "strengthA": state.strength_a,
                "strengthB": state.strength_b,
                "limitA": state.limit_a,
                "limitB": state.limit_b,
            },
        )
        return
    if len(raw) < 3:
        return
    channel, strength_mode, strength = raw[0], raw[1], raw[2]
    value = int(strength)
    logger.debug("Strength changing: %s--%s--%s", channel, strength_mode, strength)
    if channel == "1":
        state.set_strength("A", value, _op_mode(strength_mode))
    elif channel == "2":
        state.set_strength("B", value, _op_mode(strength_mode))


def _op_mode(strength_mode: str) -> str:
    return {"0": "sub", "1": "add", "2": "set"}.get(strength_mode, "set")


def _pulse(message: str, state: AppState) -> None:
    channel, _, wave_json = message.partition(":")
    wave_set = json.loads(wave_json)
    logger.debug("Pulse changing: %s", channel)
    dglab_wave_handler(state, wave_set, channel, state.wave_convert_ratio)


def _clear(message: str, state: AppState) -> None:
    if message == "1":
        state.wave_a = list(DEFAULT_WAVE)
        state.strength_a = 0
    elif message == "2":
        state.wave_b = list(DEFAULT_WAVE)
        state.strength_b = 0
