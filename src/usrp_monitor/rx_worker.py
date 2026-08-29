"""Background RX thread, command queue, and IQ ring buffer."""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from usrp_monitor.device import (
    DEFAULT_ANTENNA,
    DEFAULT_FREQ_HZ,
    DEFAULT_GAIN_DB,
    DEFAULT_RATE_HZ,
    DEFAULT_UHD_ARGS,
    DeviceStatus,
    MockRxDevice,
    UsrpRxDevice,
)


@dataclass
class WorkerSnapshot:
    samples: np.ndarray
    status: DeviceStatus
    power_peak_dbfs: float = -120.0
    power_rms_dbfs: float = -120.0


class IqRing:
    def __init__(self, capacity: int) -> None:
        self.capacity = int(capacity)
        self._buf = np.zeros(self.capacity, dtype=np.complex64)
        self._write = 0
        self._filled = 0
        self._lock = threading.Lock()

    def write(self, samples: np.ndarray) -> None:
        if samples.size == 0:
            return
        with self._lock:
            n = int(samples.size)
            if n >= self.capacity:
                self._buf[:] = samples[-self.capacity :]
                self._write = 0
                self._filled = self.capacity
                return
            end = self._write + n
            if end <= self.capacity:
                self._buf[self._write : end] = samples
            else:
                first = self.capacity - self._write
                self._buf[self._write :] = samples[:first]
                self._buf[: n - first] = samples[first:]
            self._write = (self._write + n) % self.capacity
            self._filled = min(self.capacity, self._filled + n)

    def latest(self, n: int) -> np.ndarray:
        with self._lock:
            take = min(int(n), self._filled)
            if take == 0:
                return np.zeros(0, dtype=np.complex64)
            start = (self._write - take) % self.capacity
            if start + take <= self.capacity:
                return self._buf[start : start + take].copy()
            first = self.capacity - start
            return np.concatenate((self._buf[start:], self._buf[: take - first]))


class RxWorker:
    """Owns all device calls on a single thread."""

    def __init__(self) -> None:
        self._commands: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        self._ring = IqRing(1 << 18)
        self._device: MockRxDevice | UsrpRxDevice | None = None
        self._status = DeviceStatus()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._chunk = 4096
        self._fft_size = 2048

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="rx-worker", daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self._commands.put(("shutdown", {}))
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

    def submit(self, name: str, **kwargs: Any) -> None:
        self._commands.put((name, kwargs))

    def snapshot(self) -> WorkerSnapshot:
        from usrp_monitor.dsp import power_stats

        samples = self._ring.latest(self._fft_size)
        peak, rms = power_stats(samples)
        return WorkerSnapshot(
            samples=samples, status=self._status, power_peak_dbfs=peak, power_rms_dbfs=rms
        )

    def _run(self) -> None:
        last_mock_time = time.perf_counter()
        while not self._stop.is_set():
            self._drain_commands()
            if self._device is None:
                time.sleep(0.02)
                continue
            status = self._device.get_status()
            last_error = self._status.last_error
            self._status = status
            if last_error and not self._status.last_error:
                self._status.last_error = last_error
            if not status.streaming:
                time.sleep(0.02)
                continue
            try:
                samples, err = self._device.recv(self._chunk, timeout=0.2)
            except Exception as exc:  # noqa: BLE001
                self._status.last_error = str(exc)
                time.sleep(0.05)
                continue
            if err and err not in ("overflow", "timeout"):
                self._status.last_error = err
            self._ring.write(samples)
            if status.mock and samples.size:
                last_mock_time = self._pace_mock(
                    last_mock_time, samples.size, status.rate_hz
                )

        self._teardown()

    def _pace_mock(self, last: float, nsamps: int, rate_hz: float) -> float:
        target = nsamps / max(rate_hz, 1.0)
        now = time.perf_counter()
        sleep_for = target - (now - last)
        if sleep_for > 0:
            time.sleep(min(sleep_for, 0.05))
            return time.perf_counter()
        return now

    def _drain_commands(self) -> None:
        while True:
            try:
                name, kwargs = self._commands.get_nowait()
            except queue.Empty:
                return
            try:
                self._handle(name, kwargs)
            except Exception as exc:  # noqa: BLE001
                self._status.last_error = str(exc)

    def _handle(self, name: str, kwargs: dict[str, Any]) -> None:
        if name == "shutdown":
            self._teardown()
            self._stop.set()
        elif name == "connect":
            self._connect(
                mock=bool(kwargs.get("mock", True)),
                args=str(kwargs.get("args", DEFAULT_UHD_ARGS)),
            )
        elif name == "disconnect":
            self._teardown()
        elif name == "configure":
            if self._device is None:
                return
            self._device.configure_rx(
                float(kwargs.get("freq_hz", DEFAULT_FREQ_HZ)),
                float(kwargs.get("rate_hz", DEFAULT_RATE_HZ)),
                float(kwargs.get("gain_db", DEFAULT_GAIN_DB)),
                str(kwargs.get("antenna", DEFAULT_ANTENNA)),
            )
            self._status = self._device.get_status()
        elif name == "start":
            if self._device is None:
                raise RuntimeError("not connected")
            self._device.start_stream()
            self._status = self._device.get_status()
        elif name == "stop":
            if self._device is not None:
                self._device.stop_stream()
                self._status = self._device.get_status()

    def _connect(self, mock: bool, args: str) -> None:
        self._teardown()
        if mock:
            dev: MockRxDevice | UsrpRxDevice = MockRxDevice()
        else:
            dev = UsrpRxDevice(args=args)
        dev.connect()
        self._device = dev
        self._status = dev.get_status()
        self._status.last_error = ""

    def _teardown(self) -> None:
        if self._device is not None:
            try:
                self._device.disconnect()
            except Exception:
                pass
        self._device = None
        self._status = DeviceStatus()
