from model import *
from utils import dglab_wave_handler

from websocket import WebSocketApp
import json
import logging


logger = logging.getLogger(__name__)


def bind(client: WebSocketApp, message: dglab_message, store: local_data):
    if message.message == "targetId":
        logger.debug("Bind received")
        store.targetId = message.clientId
        reply = {
            "type": "bind",
            "clientId": store.clientId,
            "targetId": store.targetId,
            "message": "DGLAB",
        }
        client.send(json.dumps(reply))
    elif message.message == "200":
        logger.info("Bind to remote success")
        if hasattr(store, "_state"):
            store._state.ws_bound = True
            store._state.push_log("log.ws_bound")
    elif message.message.isdigit() and int(message.message) in code:
        error_code = int(message.message)
        err_key = code[error_code][0]
        logger.error(err_key)
        if hasattr(store, "_state"):
            store._state.last_error = err_key
            store._state.push_log("log.bind_error", {"error": err_key})


def heartbeat(client: WebSocketApp, message: dglab_message, store: local_data):
    msg = int(message.message)
    if msg == 200:
        logger.debug("Heartbeating...")
        client.send(
            json.dumps(
                {
                    "type": "heartbeat",
                    "clientId": store.clientId,
                    "targetId": store.targetId,
                    "message": 200,
                }
            )
        )
        return
    if msg in code:
        err_key = code[msg][0]
        logger.error(err_key)
        if hasattr(store, "_state"):
            store._state.last_error = err_key
        return
    logger.error("Unknown heartbeat message: %s", message.message)
    raise Exception("Unknown heartbeat message: " + str(message.message))


def msg(client: WebSocketApp, message: dglab_message, store: local_data):
    parts = message.message.split("-", 1)
    if len(parts) < 2:
        return
    message_type, message_content = parts[0], parts[1]
    if message_type == "strength":
        _strength(message_content, store)
    elif message_type == "pulse":
        ratio = 5
        if hasattr(store, "_state"):
            ratio = store._state.wave_convert_ratio
        _pulse(message_content, store, ratio)
    elif message_type == "clear":
        _clear(message_content, store)


def strength_upload(client: WebSocketApp, message: str, store: local_data):
    reply = {
        "type": "msg",
        "clientId": store.clientId,
        "targetId": store.targetId,
        "message": message,
    }
    client.send(json.dumps(reply))


def break_(client: WebSocketApp, message: dglab_message):
    raise Exception("Connection broken")


def error(client: WebSocketApp, message: dglab_message):
    pass


def response(client: WebSocketApp, message: str, store: local_data):
    reply = {
        "type": "msg",
        "clientId": store.clientId,
        "targetId": store.targetId,
        "message": message,
    }
    client.send(json.dumps(reply))


def _strength(message: str, store: local_data):
    raw = message.split("+")
    if len(raw) < 3:
        return
    channel, strength_mode, strength = raw[0], raw[1], raw[2]
    value = int(strength)
    logger.debug("Strength changing: %s--%s--%s", channel, strength_mode, strength)

    if channel == "1":
        if strength_mode == "0":
            store.channelAStrength = max(0, store.channelAStrength - value)
        elif strength_mode == "1":
            store.channelAStrength = min(store.limitA, store.channelAStrength + value)
        elif strength_mode == "2":
            store.channelAStrength = max(0, min(store.limitA, value))
    elif channel == "2":
        if strength_mode == "0":
            store.channelBStrength = max(0, store.channelBStrength - value)
        elif strength_mode == "1":
            store.channelBStrength = min(store.limitB, store.channelBStrength + value)
        elif strength_mode == "2":
            store.channelBStrength = max(0, min(store.limitB, value))


def _pulse(message: str, store: local_data, wave_convert_ratio: int = 5):
    channel = message.split(":")[0]
    wave_set = json.loads(message.split(":", 1)[1])
    logger.debug("Pulse changing: %s--%s", channel, wave_set)
    dglab_wave_handler(store, wave_set, channel, wave_convert_ratio)


def _clear(message: str, store: local_data):
    channel = message
    if channel == "1":
        store.channelAWave = [(5, 95, 20)]
        store.channelAStrength = 0
    elif channel == "2":
        store.channelBWave = [(5, 95, 20)]
        store.channelBStrength = 0
