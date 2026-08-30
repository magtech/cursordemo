"""RX device backends: UHD B205mini-i and a mock tone generator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

DEFAULT_FREQ_HZ = 100e6
DEFAULT_RATE_HZ = 2e6
DEFAULT_GAIN_DB = 38.0
DEFAULT_ANTENNA = "RX2"
DEFAULT_UHD_ARGS = "type=b200"
CHANNEL = 0


@dataclass
class DeviceStatus:
    connected: bool = False
    streaming: bool = False
    mock: bool = False
    name: str = ""
    serial: str = ""
    usb_speed: str = ""
    freq_hz: float = DEFAULT_FREQ_HZ
    rate_hz: float = DEFAULT_RATE_HZ
    gain_db: float = DEFAULT_GAIN_DB
    antenna: str = DEFAULT_ANTENNA
    gain_min_db: float = 0.0
    gain_max_db: float = 76.0
    last_error: str = ""
    overflows: int = 0
    timeouts: int = 0
    extra: dict[str, str] = field(default_factory=dict)


class RxDevice(Protocol):
    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def configure_rx(
        self, freq_hz: float, rate_hz: float, gain_db: float, antenna: str
    ) -> None: ...
    def start_stream(self) -> None: ...
    def stop_stream(self) -> None: ...
    def recv(self, nsamps: int, timeout: float = 1.0) -> tuple[np.ndarray, str]: ...
    def get_status(self) -> DeviceStatus: ...


class MockRxDevice:
    """Generates a complex tone plus noise at the configured sample rate."""

    def __init__(self) -> None:
        self._connected = False
        self._streaming = False
        self._freq_hz = DEFAULT_FREQ_HZ
        self._rate_hz = DEFAULT_RATE_HZ
        self._gain_db = DEFAULT_GAIN_DB
        self._antenna = DEFAULT_ANTENNA
        self._phase = 0.0
        self._tone_offset_hz = 200e3
        rng = np.random.default_rng(0)
        self._rng = rng

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self.stop_stream()
        self._connected = False

    def configure_rx(
        self, freq_hz: float, rate_hz: float, gain_db: float, antenna: str
    ) -> None:
        if rate_hz <= 0:
            raise ValueError("sample rate must be positive")
        self._freq_hz = float(freq_hz)
        self._rate_hz = float(rate_hz)
        self._gain_db = float(gain_db)
        self._antenna = antenna

    def start_stream(self) -> None:
        if not self._connected:
            raise RuntimeError("mock device is not connected")
        self._streaming = True
        self._phase = 0.0

    def stop_stream(self) -> None:
        self._streaming = False

    def recv(self, nsamps: int, timeout: float = 1.0) -> tuple[np.ndarray, str]:
        del timeout
        if not self._streaming:
            return np.zeros(0, dtype=np.complex64), ""
        n = int(nsamps)
        t = np.arange(n, dtype=np.float64) / self._rate_hz
        omega = 2.0 * np.pi * self._tone_offset_hz
        phase = self._phase + omega * t
        # Map gain 0–76 dB to a modest amplitude so plots look similar to hardware.
        amp = 0.05 * (10 ** (min(self._gain_db, 76.0) / 40.0))
        amp = min(amp, 0.7)
        tone = amp * np.exp(1j * phase)
        noise = 0.02 * (
            self._rng.standard_normal(n) + 1j * self._rng.standard_normal(n)
        )
        self._phase = (self._phase + omega * n / self._rate_hz) % (2.0 * np.pi)
        return (tone + noise).astype(np.complex64), ""

    def get_status(self) -> DeviceStatus:
        return DeviceStatus(
            connected=self._connected,
            streaming=self._streaming,
            mock=True,
            name="Mock B205mini-i",
            serial="MOCK",
            usb_speed="n/a",
            freq_hz=self._freq_hz,
            rate_hz=self._rate_hz,
            gain_db=self._gain_db,
            antenna=self._antenna,
            gain_min_db=0.0,
            gain_max_db=76.0,
        )


class UsrpRxDevice:
    """UHD wrapper for a B200-series USRP (B205mini-i)."""

    def __init__(self, args: str = DEFAULT_UHD_ARGS) -> None:
        self._args = args
        self._usrp = None
        self._streamer = None
        self._metadata = None
        self._recv_buffer: np.ndarray | None = None
        self._streaming = False
        self._freq_hz = DEFAULT_FREQ_HZ
        self._rate_hz = DEFAULT_RATE_HZ
        self._gain_db = DEFAULT_GAIN_DB
        self._antenna = DEFAULT_ANTENNA
        self._overflows = 0
        self._timeouts = 0
        self._last_error = ""

    def connect(self) -> None:
        import uhd

        self._usrp = uhd.usrp.MultiUSRP(self._args)
        self._metadata = uhd.types.RXMetadata()
        self.configure_rx(self._freq_hz, self._rate_hz, self._gain_db, self._antenna)

    def disconnect(self) -> None:
        self.stop_stream()
        self._usrp = None
        self._streamer = None
        self._metadata = None
        self._recv_buffer = None

    def configure_rx(
        self, freq_hz: float, rate_hz: float, gain_db: float, antenna: str
    ) -> None:
        import uhd

        if self._usrp is None:
            self._freq_hz = float(freq_hz)
            self._rate_hz = float(rate_hz)
            self._gain_db = float(gain_db)
            self._antenna = antenna
            return

        restart = self._streaming and abs(rate_hz - self._rate_hz) > 1.0
        if restart:
            self.stop_stream()

        self._usrp.set_rx_rate(float(rate_hz), CHANNEL)
        self._usrp.set_rx_freq(uhd.types.TuneRequest(float(freq_hz)), CHANNEL)
        self._usrp.set_rx_gain(float(gain_db), CHANNEL)
        try:
            self._usrp.set_rx_antenna(antenna, CHANNEL)
        except Exception as exc:  # noqa: BLE001 — UHD raises various types
            self._last_error = f"antenna: {exc}"

        self._freq_hz = float(self._usrp.get_rx_freq(CHANNEL))
        self._rate_hz = float(self._usrp.get_rx_rate(CHANNEL))
        self._gain_db = float(self._usrp.get_rx_gain(CHANNEL))
        try:
            self._antenna = str(self._usrp.get_rx_antenna(CHANNEL))
        except Exception:
            self._antenna = antenna

        if restart:
            self.start_stream()

    def start_stream(self) -> None:
        import uhd

        if self._usrp is None:
            raise RuntimeError("USRP is not connected")
        if self._streaming:
            return

        st_args = uhd.usrp.StreamArgs("fc32", "sc16")
        st_args.channels = [CHANNEL]
        self._streamer = self._usrp.get_rx_stream(st_args)
        max_samps = int(self._streamer.get_max_num_samps())
        self._recv_buffer = np.zeros((1, max_samps), dtype=np.complex64)

        cmd = uhd.types.StreamCMD(uhd.types.StreamMode.start_cont)
        cmd.stream_now = True
        self._streamer.issue_stream_cmd(cmd)
        self._streaming = True

    def stop_stream(self) -> None:
        if not self._streaming or self._streamer is None:
            self._streaming = False
            return
        import uhd

        cmd = uhd.types.StreamCMD(uhd.types.StreamMode.stop_cont)
        try:
            self._streamer.issue_stream_cmd(cmd)
        except Exception:
            pass
        self._streaming = False
        self._streamer = None

    def recv(self, nsamps: int, timeout: float = 1.0) -> tuple[np.ndarray, str]:
        import uhd

        if not self._streaming or self._streamer is None or self._recv_buffer is None:
            return np.zeros(0, dtype=np.complex64), ""

        want = int(nsamps)
        out = np.empty(want, dtype=np.complex64)
        got = 0
        err = ""
        while got < want:
            chunk = min(want - got, self._recv_buffer.shape[1])
            n = int(
                self._streamer.recv(
                    self._recv_buffer[:, :chunk], self._metadata, timeout
                )
            )
            code = self._metadata.error_code
            if code == uhd.types.RXMetadataErrorCode.overflow:
                self._overflows += 1
                err = "overflow"
            elif code == uhd.types.RXMetadataErrorCode.timeout:
                self._timeouts += 1
                err = "timeout"
                break
            elif code != uhd.types.RXMetadataErrorCode.none:
                err = self._metadata.strerror()
                self._last_error = err
            if n <= 0:
                break
            out[got : got + n] = self._recv_buffer[0, :n]
            got += n
        return out[:got], err

    def get_status(self) -> DeviceStatus:
        name = ""
        serial = ""
        usb_speed = ""
        extra: dict[str, str] = {}
        gmin, gmax = 0.0, 76.0
        if self._usrp is not None:
            try:
                info = self._usrp.get_usrp_rx_info(CHANNEL)
                name = _info_get(info, "mboard_id", "mboard_name")
                serial = _info_get(info, "mboard_serial")
                extra["rx_subdev"] = _info_get(info, "rx_subdev_name")
            except Exception:
                try:
                    name = str(self._usrp.get_mboard_name())
                except Exception:
                    name = "USRP"
            try:
                sensor = self._usrp.get_mboard_sensor("usb_speed", 0)
                usb_speed = str(sensor)
            except Exception:
                usb_speed = ""
            try:
                gr = self._usrp.get_rx_gain_range(CHANNEL)
                gmin = float(gr.start())
                gmax = float(gr.stop())
            except Exception:
                pass
            try:
                self._freq_hz = float(self._usrp.get_rx_freq(CHANNEL))
                self._rate_hz = float(self._usrp.get_rx_rate(CHANNEL))
                self._gain_db = float(self._usrp.get_rx_gain(CHANNEL))
            except Exception:
                pass

        return DeviceStatus(
            connected=self._usrp is not None,
            streaming=self._streaming,
            mock=False,
            name=name or "USRP B200",
            serial=serial,
            usb_speed=usb_speed,
            freq_hz=self._freq_hz,
            rate_hz=self._rate_hz,
            gain_db=self._gain_db,
            antenna=self._antenna,
            gain_min_db=gmin,
            gain_max_db=gmax,
            last_error=self._last_error,
            overflows=self._overflows,
            timeouts=self._timeouts,
            extra=extra,
        )


def _info_get(info: object, *keys: str) -> str:
    for key in keys:
        try:
            if hasattr(info, "get"):
                value = info.get(key)  # type: ignore[attr-defined]
            else:
                value = info[key]  # type: ignore[index]
            if value:
                return str(value)
        except Exception:
            continue
    return ""


def uhd_available() -> bool:
    try:
        import uhd  # noqa: F401
    except Exception:
        return False
    return True
