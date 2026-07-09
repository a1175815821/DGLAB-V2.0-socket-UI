import asyncio
import logging
import threading
from typing import Optional

import pydglab

from model import AppState

logger = logging.getLogger(__name__)


class DeviceService:
    def __init__(self, state: AppState):
        self.state = state
        self._dglab: Optional[pydglab.dglab] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> dict:
        with self._lock:
            if self.is_running and self.state.device_connected:
                return {"ok": True, "already": True}
            if self.is_running:
                self._stop_unlocked(timeout=3)

            self._stop.clear()
            self.state.device_connecting = True
            self.state.device_connected = False
            self.state.device_error = ""
            self.state.push_log("log.device_connecting")
            self._thread = threading.Thread(
                target=self._run_loop, daemon=True, name="device-loop"
            )
            self._thread.start()
            return {"ok": True, "already": False}

    def stop(self) -> None:
        with self._lock:
            self._stop_unlocked(timeout=5)

    def _stop_unlocked(self, timeout: float = 5) -> None:
        """Signal worker to close BLE and wait for thread exit."""
        self._stop.set()
        self.state.device_connecting = False

        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=timeout)
            if thread.is_alive():
                logger.warning("Device thread did not exit within %.1fs", timeout)

        self._thread = None
        self._dglab = None
        self._loop = None
        self.state.device_connected = False
        self.state.device_connecting = False

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception as e:
            logger.exception("Device loop crashed")
            self.state.device_connected = False
            self.state.device_connecting = False
            self.state.device_error = str(e)
            self.state.push_log("log.device_error", {"error": str(e)})
        finally:
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception:
                pass
            try:
                self._loop.close()
            except Exception:
                pass
            self._loop = None
            self._dglab = None

    async def _close_device(self) -> None:
        dglab = self._dglab
        if dglab is None:
            return
        try:
            try:
                await dglab.set_strength_sync(0, 0)
            except Exception as e:
                logger.debug("Zero strength failed: %s", e)
            try:
                await dglab.close()
                logger.info("Device BLE closed")
            except Exception as e:
                logger.warning("dglab.close failed: %s", e)
                client = getattr(dglab, "client", None)
                if client is not None:
                    try:
                        await client.disconnect()
                        logger.info("Device BLE disconnected via client")
                    except Exception as e2:
                        logger.warning("client.disconnect failed: %s", e2)
        finally:
            self._dglab = None
            self.state.strength_a = 0
            self.state.strength_b = 0
            self.state.device_connected = False
            self.state.device_connecting = False

    async def _main(self) -> None:
        try:
            self._dglab = pydglab.dglab()
            await self._dglab.create()
            if self._stop.is_set():
                await self._close_device()
                return
            self.state.device_connected = True
            self.state.device_connecting = False
            self.state.device_error = ""
            self.state.push_log("log.device_connected")
        except Exception as e:
            self.state.device_connected = False
            self.state.device_connecting = False
            self.state.device_error = str(e)
            self.state.push_log("log.device_connect_failed", {"error": str(e)})
            while not self._stop.is_set():
                await asyncio.sleep(0.2)
            return

        try:
            while not self._stop.is_set():
                try:
                    self.state.clamp_strength()
                    await self._dglab.set_strength_sync(
                        self.state.strength_a, self.state.strength_b
                    )
                    await self._dglab.set_wave_set_sync(
                        self.state.wave_a, self.state.wave_b
                    )
                    if not self.state.device_connected:
                        self.state.device_connected = True
                        self.state.device_error = ""
                except Exception as e:
                    self.state.device_connected = False
                    self.state.device_error = str(e)
                    self.state.push_log("log.device_write_failed", {"error": str(e)})
                await asyncio.sleep(0.1)
        finally:
            # Always close BLE when leaving the loop
            await self._close_device()
