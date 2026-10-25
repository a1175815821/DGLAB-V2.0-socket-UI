import asyncio
import logging
import threading

import pydglab

from model import AppState

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 0.1
ERROR_BACKOFF_S = 1.0


class DeviceService:
    """Owns the BLE connection and keeps hardware in sync with AppState.

    A worker thread runs its own asyncio loop. ``start()`` may be called while
    a previous worker is still dying (BLE cleanup can block), so every worker
    carries a generation number and only touches shared state while it is the
    current one.
    """

    def __init__(self, state: AppState):
        self.state = state
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._generation = 0

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> dict:
        with self._lock:
            if self.is_running and self.state.device_connected:
                return {"ok": True, "already": True}
            if self.is_running:
                self._stop_unlocked(timeout=3)

            self._generation += 1
            generation = self._generation
            self._stop.clear()
            self.state.device_connecting = True
            self.state.device_connected = False
            self.state.device_error = ""
            self.state.push_log("log.device_connecting")
            self._thread = threading.Thread(
                target=self._run_loop, args=(generation,), daemon=True, name="device-loop"
            )
            self._thread.start()
            return {"ok": True, "already": False}

    def stop(self) -> None:
        with self._lock:
            self._stop_unlocked(timeout=5)

    def _stop_unlocked(self, timeout: float = 5) -> None:
        """Signal the worker to close BLE and wait for it to exit."""
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=timeout)
            if thread.is_alive():
                logger.warning("Device thread did not exit within %.1fs", timeout)
        self._thread = None
        self.state.device_connected = False
        self.state.device_connecting = False

    def _run_loop(self, generation: int) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._main(generation))
        except Exception as e:
            logger.exception("Device loop crashed")
            if generation == self._generation:
                self.state.device_connected = False
                self.state.device_connecting = False
                self.state.device_error = str(e)
                self.state.push_log("log.device_error", {"error": str(e)})
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception:
                pass
            try:
                loop.close()
            except Exception:
                pass

    async def _close_device(self, dglab) -> None:
        if dglab is None:
            return
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

    async def _main(self, generation: int) -> None:
        dglab = None
        connected = False
        try:
            dglab = pydglab.dglab()
            await dglab.create()
            if self._stop.is_set() or generation != self._generation:
                return  # superseded or stopped while connecting; finally closes BLE
            connected = True
            self.state.device_connected = True
            self.state.device_connecting = False
            self.state.device_error = ""
            self.state.push_log("log.device_connected")
            await self._sync_loop(dglab)
        except Exception as e:
            logger.exception("Device loop crashed")
            if generation == self._generation:
                self.state.device_connected = False
                self.state.device_connecting = False
                self.state.device_error = str(e)
                self.state.push_log(
                    "log.device_connect_failed" if not connected else "log.device_error",
                    {"error": str(e)},
                )
        finally:
            await self._close_device(dglab)
            if generation == self._generation:
                self.state.strength_a = 0
                self.state.strength_b = 0
                self.state.device_connected = False
                self.state.device_connecting = False

    async def _sync_loop(self, dglab) -> None:
        last_strength: tuple[int, int] | None = None
        last_wave: tuple[list, list] | None = None
        last_error = ""
        while not self._stop.is_set():
            try:
                self.state.clamp_strength()
                strength = (self.state.strength_a, self.state.strength_b)
                wave = (self.state.wave_a, self.state.wave_b)
                # The BLE link only needs writes when something changed;
                # pydglab's internal task streams the wave set on its own.
                if strength != last_strength:
                    await dglab.set_strength_sync(*strength)
                    last_strength = strength
                if wave != last_wave:
                    await dglab.set_wave_set_sync(*wave)
                    last_wave = wave
                if not self.state.device_connected:
                    self.state.device_connected = True
                    self.state.device_error = ""
                last_error = ""
            except Exception as e:
                err = str(e)
                self.state.device_connected = False
                self.state.device_error = err
                # Invalidate caches so a recovered link resends state.
                last_strength = None
                last_wave = None
                if err != last_error:
                    self.state.push_log("log.device_write_failed", {"error": err})
                    last_error = err
                await asyncio.sleep(ERROR_BACKOFF_S)
                continue
            await asyncio.sleep(POLL_INTERVAL_S)
