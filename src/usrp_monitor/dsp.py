"""FFT / power helpers for complex IQ."""

from __future__ import annotations

import numpy as np

EPS = 1e-20


def hann_window(n: int) -> np.ndarray:
    win_fn = getattr(np, "hann", np.hanning)
    return win_fn(n).astype(np.float64)


def psd_dbfs(samples: np.ndarray, fft_size: int) -> np.ndarray:
    """Two-sided power spectrum in dBFS (full scale = |x| = 1)."""
    n = min(len(samples), fft_size)
    if n < 8:
        return np.full(fft_size, -120.0, dtype=np.float64)
    x = np.zeros(fft_size, dtype=np.complex128)
    x[:n] = samples[:n]
    win = hann_window(fft_size)
    scale = float(np.sum(win))
    spec = np.fft.fftshift(np.fft.fft(x * win))
    mag = np.abs(spec) / scale
    return (20.0 * np.log10(np.maximum(mag, EPS))).astype(np.float64)


def rf_freq_axis(fft_size: int, rate_hz: float, center_hz: float) -> np.ndarray:
    baseband = np.fft.fftshift(np.fft.fftfreq(fft_size, d=1.0 / rate_hz))
    return baseband + center_hz


def power_stats(samples: np.ndarray) -> tuple[float, float]:
    """Return (peak_dbfs, rms_dbfs)."""
    if samples.size == 0:
        return -120.0, -120.0
    mag2 = np.abs(samples) ** 2
    peak = float(np.sqrt(np.max(mag2)))
    rms = float(np.sqrt(np.mean(mag2)))
    peak_db = 20.0 * np.log10(max(peak, EPS))
    rms_db = 20.0 * np.log10(max(rms, EPS))
    return peak_db, rms_db
