"""PyQt6 monitor window."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from usrp_monitor.device import (
    DEFAULT_ANTENNA,
    DEFAULT_FREQ_HZ,
    DEFAULT_GAIN_DB,
    DEFAULT_RATE_HZ,
    DEFAULT_UHD_ARGS,
)
from usrp_monitor.dsp import psd_dbfs, rf_freq_axis
from usrp_monitor.rx_worker import RxWorker

FFT_SIZE = 2048
WATERFALL_ROWS = 160
UI_HZ = 25


def _fmt_hz(hz: float) -> str:
    ah = abs(hz)
    if ah >= 1e6:
        return f"{hz / 1e6:.6g} MHz"
    if ah >= 1e3:
        return f"{hz / 1e3:.6g} kHz"
    return f"{hz:.3g} Hz"


class MonitorWindow(QMainWindow):
    def __init__(self, prefer_mock: bool, force_hardware: bool) -> None:
        super().__init__()
        self.setWindowTitle("USRP B205mini-i RX Monitor")
        self.resize(1280, 800)
        self._prefer_mock = prefer_mock
        self._force_hardware = force_hardware
        self._worker = RxWorker()
        self._worker._fft_size = FFT_SIZE
        self._worker.start()
        self._waterfall = np.full((WATERFALL_ROWS, FFT_SIZE), -120.0)

        pg.setConfigOptions(antialias=True, foreground="d", background="#121212")

        root = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(self._build_controls())
        root.addWidget(self._build_plots())
        root.setStretchFactor(0, 0)
        root.setStretchFactor(1, 1)
        root.setSizes([320, 960])
        self.setCentralWidget(root)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(int(1000 / UI_HZ))

        from usrp_monitor.device import uhd_available

        if prefer_mock or (not force_hardware and not uhd_available()):
            self._source.setCurrentText("Mock")
        else:
            self._source.setCurrentText("Hardware (UHD)")

    def closeEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        self._worker.shutdown()
        super().closeEvent(event)

    def _build_controls(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        conn = QGroupBox("Device")
        form = QFormLayout(conn)
        self._source = QComboBox()
        self._source.addItems(["Mock", "Hardware (UHD)"])
        self._args = QLineEdit(DEFAULT_UHD_ARGS)
        form.addRow("Source", self._source)
        form.addRow("UHD args", self._args)
        row = QHBoxLayout()
        self._connect_btn = QPushButton("Connect")
        self._disconnect_btn = QPushButton("Disconnect")
        self._connect_btn.clicked.connect(self._on_connect)
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        row.addWidget(self._connect_btn)
        row.addWidget(self._disconnect_btn)
        form.addRow(row)
        layout.addWidget(conn)

        rx = QGroupBox("RX")
        rx_form = QFormLayout(rx)
        self._freq = QDoubleSpinBox()
        self._freq.setDecimals(0)
        self._freq.setRange(70e6, 6e9)
        self._freq.setSingleStep(1e6)
        self._freq.setValue(DEFAULT_FREQ_HZ)
        self._freq.setSuffix(" Hz")
        self._rate = QDoubleSpinBox()
        self._rate.setDecimals(0)
        self._rate.setRange(1e5, 56e6)
        self._rate.setSingleStep(1e6)
        self._rate.setValue(DEFAULT_RATE_HZ)
        self._rate.setSuffix(" Hz")
        self._gain = QDoubleSpinBox()
        self._gain.setRange(0.0, 76.0)
        self._gain.setDecimals(1)
        self._gain.setValue(DEFAULT_GAIN_DB)
        self._gain.setSuffix(" dB")
        self._antenna = QComboBox()
        self._antenna.addItems(["RX2", "TX/RX"])
        self._antenna.setCurrentText(DEFAULT_ANTENNA)
        rx_form.addRow("Center", self._freq)
        rx_form.addRow("Sample rate", self._rate)
        rx_form.addRow("RX gain", self._gain)
        rx_form.addRow("Antenna", self._antenna)
        apply_row = QHBoxLayout()
        self._apply_btn = QPushButton("Apply tune")
        self._start_btn = QPushButton("Start RX")
        self._stop_btn = QPushButton("Stop RX")
        self._apply_btn.clicked.connect(self._on_apply)
        self._start_btn.clicked.connect(self._on_start)
        self._stop_btn.clicked.connect(self._on_stop)
        apply_row.addWidget(self._apply_btn)
        rx_form.addRow(apply_row)
        stream_row = QHBoxLayout()
        stream_row.addWidget(self._start_btn)
        stream_row.addWidget(self._stop_btn)
        rx_form.addRow(stream_row)
        layout.addWidget(rx)

        st = QGroupBox("Status")
        st_form = QFormLayout(st)
        self._st_connected = QLabel("no")
        self._st_name = QLabel("—")
        self._st_serial = QLabel("—")
        self._st_usb = QLabel("—")
        self._st_freq = QLabel("—")
        self._st_rate = QLabel("—")
        self._st_gain = QLabel("—")
        self._st_power = QLabel("—")
        self._st_errors = QLabel("overflows 0 / timeouts 0")
        self._st_last = QLabel("—")
        self._st_last.setWordWrap(True)
        st_form.addRow("Connected", self._st_connected)
        st_form.addRow("Name", self._st_name)
        st_form.addRow("Serial", self._st_serial)
        st_form.addRow("USB", self._st_usb)
        st_form.addRow("Actual freq", self._st_freq)
        st_form.addRow("Actual rate", self._st_rate)
        st_form.addRow("Actual gain", self._st_gain)
        st_form.addRow("Power", self._st_power)
        st_form.addRow("Stream", self._st_errors)
        st_form.addRow("Last error", self._st_last)
        layout.addWidget(st)
        layout.addStretch(1)
        return panel

    def _build_plots(self) -> QWidget:
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        splitter = QSplitter(Qt.Orientation.Vertical)

        self._spec_plot = pg.PlotWidget(title="Spectrum")
        self._spec_plot.setLabel("bottom", "Frequency", units="Hz")
        self._spec_plot.setLabel("left", "Power", units="dBFS")
        self._spec_plot.setYRange(-120, 0)
        self._spec_curve = self._spec_plot.plot(pen=pg.mkPen("#5b9cf5", width=1.5))

        self._wf_plot = pg.PlotWidget(title="Waterfall")
        self._wf_plot.setLabel("bottom", "Frequency", units="Hz")
        self._wf_plot.setLabel("left", "Time", units="frames")
        self._wf_img = pg.ImageItem(axisOrder="row-major")
        self._wf_plot.addItem(self._wf_img)
        try:
            cmap = pg.colormap.get("CET-L17")
            self._wf_img.setLookupTable(cmap.getLookupTable(nPts=256))
        except Exception:
            pass
        self._wf_img.setLevels((-90, 0))

        self._iq_plot = pg.PlotWidget(title="Time (I / Q)")
        self._iq_plot.setLabel("bottom", "Sample")
        self._iq_plot.setLabel("left", "Amplitude")
        self._i_curve = self._iq_plot.plot(pen=pg.mkPen("#7dce82", width=1), name="I")
        self._q_curve = self._iq_plot.plot(pen=pg.mkPen("#e07a5f", width=1), name="Q")
        self._iq_plot.addLegend()

        splitter.addWidget(self._spec_plot)
        splitter.addWidget(self._wf_plot)
        splitter.addWidget(self._iq_plot)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 1)
        v.addWidget(splitter)
        return wrap

    def _on_connect(self) -> None:
        mock = self._source.currentText() == "Mock"
        if not mock:
            from usrp_monitor.device import uhd_available

            if not uhd_available():
                QMessageBox.warning(
                    self,
                    "UHD missing",
                    "The uhd Python package is not importable. "
                    "Install matching UHD + pip uhd, or use Mock.",
                )
                return
        self._worker.submit("connect", mock=mock, args=self._args.text().strip())
        self._on_apply()

    def _on_disconnect(self) -> None:
        self._worker.submit("disconnect")

    def _on_apply(self) -> None:
        self._worker.submit(
            "configure",
            freq_hz=self._freq.value(),
            rate_hz=self._rate.value(),
            gain_db=self._gain.value(),
            antenna=self._antenna.currentText(),
        )

    def _on_start(self) -> None:
        self._on_apply()
        self._worker.submit("start")

    def _on_stop(self) -> None:
        self._worker.submit("stop")

    def _on_tick(self) -> None:
        snap = self._worker.snapshot()
        st = snap.status
        src = "mock" if st.mock else "hardware"
        self._st_connected.setText(
            f"yes ({src})" if st.connected else "no"
        )
        self._st_name.setText(st.name or "—")
        self._st_serial.setText(st.serial or "—")
        self._st_usb.setText(st.usb_speed or "—")
        self._st_freq.setText(_fmt_hz(st.freq_hz))
        self._st_rate.setText(_fmt_hz(st.rate_hz))
        self._st_gain.setText(f"{st.gain_db:.1f} dB")
        self._st_power.setText(
            f"peak {snap.power_peak_dbfs:.1f} dBFS  RMS {snap.power_rms_dbfs:.1f} dBFS"
        )
        self._st_errors.setText(
            f"overflows {st.overflows} / timeouts {st.timeouts}"
            + ("  streaming" if st.streaming else "")
        )
        self._st_last.setText(st.last_error or "—")

        samples = snap.samples
        if samples.size < 32:
            return
        n = min(FFT_SIZE, samples.size)
        block = samples[-n:]
        psd = psd_dbfs(block, FFT_SIZE)
        freqs = rf_freq_axis(FFT_SIZE, st.rate_hz or DEFAULT_RATE_HZ, st.freq_hz)
        self._spec_curve.setData(freqs, psd)

        self._waterfall = np.roll(self._waterfall, -1, axis=0)
        self._waterfall[-1] = psd
        x0 = float(freqs[0])
        dx = float(freqs[1] - freqs[0]) if len(freqs) > 1 else 1.0
        self._wf_img.setImage(self._waterfall, autoLevels=False, levels=(-90, 0))
        self._wf_img.setRect(QRectF(x0, 0, dx * FFT_SIZE, WATERFALL_ROWS))

        idx = np.arange(block.size)
        self._i_curve.setData(idx, np.real(block))
        self._q_curve.setData(idx, np.imag(block))
