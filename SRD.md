# Software Requirements Document (SRD)

**Product:** USRP B205mini-i RX Monitor  
**Document status:** Draft  
**Version:** 0.1.0-draft  
**Date:** 2026-08-30  

This is a working draft. Requirement IDs are stable so later features can be appended without rewriting the prototype baseline. Items marked **Draft / TBD** are not committed for the current release.

---

## 1. Introduction

### 1.1 Purpose

Specify software requirements for a desktop application that connects to an Ettus Research **USRP B205mini-i** and provides visual monitoring of receiver parameters and sampled input.

### 1.2 Intended readers

Hardware operators, developers, and reviewers of later feature additions (transmit, firmware/FPGA selection, recording, and other UHD controls).

### 1.3 Definitions

| Term | Meaning |
| --- | --- |
| USRP | Universal Software Radio Peripheral |
| B205mini-i | USB 3.0 1×RX / 1×TX SDR (UHD device type `b200`) |
| UHD | USRP Hardware Driver (Ettus/NI) |
| IQ | Complex baseband samples (in-phase / quadrature) |
| dBFS | Decibels relative to full scale (`\|x\| = 1`) |
| Mock device | Software radio used when hardware or UHD is unavailable |

### 1.4 References

- Ettus UHD B2x0 device notes (master clock, analog bandwidth, image args `fw` / `fpga`)
- Application README (install, Windows UHD matching, run modes)
- Package `usrp-monitor` version 0.1.0

---

## 2. Scope

### 2.1 In scope (prototype baseline)

A **receive-only** local desktop application that:

- Opens a B205mini-i through UHD, or a mock radio
- Lets the operator set RX center frequency, sample rate, gain, and antenna
- Streams IQ and displays spectrum, waterfall, and time-domain I/Q
- Shows device identity and stream health

### 2.2 Out of scope (current draft)

The following are **not** required for the prototype. They may be added as new requirement IDs later:

- Transmit streaming or TX parameter control
- IQ file recording / playback
- Demodulation, decoding, or protocol analysis
- GNU Radio, web UI, or remote (non-local) control
- Multi-device / MIMO operation
- Persistent flash programming of non-B200 devices via `uhd_image_loader`
- EEPROM / FX3 recovery (`b2xx_fx3_utils`)
- GPSDO (not assumed on B205mini-i)
- Guaranteed operation above a few Msps (prototype default is 2 Msps)

---

## 3. System context

```text
[Operator] <-> [Desktop UI] <-> [RX worker thread] <-> [Device layer]
                                                      |            |
                                               [UHD / USB3]   [Mock IQ]
                                                      |
                                               [B205mini-i]
```

- All UHD calls run on a single worker thread.
- The UI reads a snapshot of the latest IQ and status on a timer (~25 Hz).

---

## 4. Hardware and environment constraints

| ID | Requirement |
| --- | --- |
| HW-1 | Target radio is USRP B205mini-i (UHD `type=b200`). |
| HW-2 | RF tune range used by the UI is 70 MHz–6 GHz. |
| HW-3 | Sample-rate control range used by the UI is 100 kHz–56 MHz analog/DSP limit; prototype default is **2 Msps**. |
| HW-4 | RX analog gain range used by the UI is 0–76 dB; default **38 dB**. |
| HW-5 | RX antenna ports are **RX2** and **TX/RX**; default **RX2**. |
| HW-6 | Host OS target is **Windows**. USB 3.0 is recommended; 2 Msps may work on USB 2.0. |
| HW-7 | Hardware mode requires host UHD installed and a **matching** Python `uhd` package. |
| HW-8 | Runtime Python is 3.10+. Official UHD wheels are typically 3.10/3.12. |
| HW-9 | Channel index is 0 (single RX). |

---

## 5. Functional requirements

Priority: **M** = must for prototype, **D** = draft/future.

### 5.1 Launch and mode selection

| ID | Pri | Requirement |
| --- | --- | --- |
| FR-LAU-1 | M | The application shall start as `python -m usrp_monitor` (or the `usrp-monitor` console script). |
| FR-LAU-2 | M | `--mock` shall force the simulated radio. |
| FR-LAU-3 | M | `--hardware` shall require the `uhd` package and shall exit with a non-zero status if it cannot be imported. |
| FR-LAU-4 | M | If neither flag is given and `uhd` is not importable, the application shall start in mock mode and print a notice. |
| FR-LAU-5 | M | Default UHD device args shall be `type=b200`. The operator may edit args (e.g. `serial=`). |

### 5.2 Connection

| ID | Pri | Requirement |
| --- | --- | --- |
| FR-CON-1 | M | The operator shall be able to connect and disconnect without restarting the process. |
| FR-CON-2 | M | Hardware connect shall construct `uhd.usrp.MultiUSRP` with the current args. |
| FR-CON-3 | M | Mock connect shall not require UHD or USB. |
| FR-CON-4 | M | If hardware `uhd` is not importable, choosing Hardware and Connect shall warn and not hang. |
| FR-CON-5 | D | Discover devices (`uhd.find` / serial pick-list) before connect. |

### 5.3 Receiver control

| ID | Pri | Requirement |
| --- | --- | --- |
| FR-RX-1 | M | The operator shall set center frequency (Hz), sample rate (Hz), RX gain (dB), and antenna. |
| FR-RX-2 | M | Apply-tune shall send those values to the device on the worker thread. |
| FR-RX-3 | M | Start RX / Stop RX shall start and stop a continuous `fc32` receive stream. |
| FR-RX-4 | M | Changing sample rate while streaming shall restart the stream if required by UHD. |
| FR-RX-5 | M | Defaults: 100 MHz, 2 Msps, 38 dB, RX2. |
| FR-RX-6 | M | Status shall show **actual** frequency, rate, and gain after coercion by the radio. |
| FR-RX-7 | D | Analog RX bandwidth (`set_rx_bandwidth`). |
| FR-RX-8 | D | RX AGC, DC offset, IQ balance, LO offset. |
| FR-RX-9 | D | Master clock rate and auto tick-rate. |
| FR-RX-10 | D | Clock/time source (`internal` / `external`). |

### 5.4 Sampled-input visualization

| ID | Pri | Requirement |
| --- | --- | --- |
| FR-VIS-1 | M | Spectrum: power (dBFS) vs **RF** frequency (not baseband-only axis). |
| FR-VIS-2 | M | Waterfall: scrolling spectrogram from the same FFT. |
| FR-VIS-3 | M | Time plot: I and Q vs sample index for the current block. |
| FR-VIS-4 | M | FFT size 2048, Hann window, ~25 Hz UI refresh. |
| FR-VIS-5 | M | Mock IQ shall include a visible tone (offset +200 kHz from center) plus noise so plots move without hardware. |
| FR-VIS-6 | D | Adjustable FFT size, averaging, and waterfall colormap/levels. |
| FR-VIS-7 | D | Constellation / spectrogram export. |

### 5.5 Status and faults

| ID | Pri | Requirement |
| --- | --- | --- |
| FR-STA-1 | M | Show connected/disconnected, mock vs hardware, device name, serial. |
| FR-STA-2 | M | Show USB speed when UHD reports it. |
| FR-STA-3 | M | Show overflow and timeout counts and streaming state. |
| FR-STA-4 | M | Show estimated in-band peak and RMS power (dBFS). |
| FR-STA-5 | M | Show last error text from connect/tune/stream failures. |
| FR-STA-6 | D | Motherboard/RX sensors (e.g. `ref_locked`, `lo_locked`) and `get_pp_string` dump. |

### 5.6 Transmit (draft)

| ID | Pri | Requirement |
| --- | --- | --- |
| FR-TX-1 | D | Set TX frequency, rate, gain, antenna, bandwidth. |
| FR-TX-2 | D | Optional TX streaming behind an explicit enable; warn that TX requires a 50 Ω load or antenna. |

### 5.7 Images / firmware (draft)

B205mini-i loads FX3 firmware and FPGA **into RAM** when `MultiUSRP` opens. Unplug/reset clears them.

| ID | Pri | Requirement |
| --- | --- | --- |
| FR-IMG-1 | D | Operator may specify `fw=` and `fpga=` in device args (or dedicated file pickers) and reconnect to load those images. |
| FR-IMG-2 | D | UI shall warn that a mismatched product image can fail the session until USB reset. |
| FR-IMG-3 | D | EEPROM init / `b2xx_fx3_utils` recovery is **not** a casual UI action. |

### 5.8 Recording and analysis (draft)

| ID | Pri | Requirement |
| --- | --- | --- |
| FR-REC-1 | D | Record IQ to file. |
| FR-REC-2 | D | Playback IQ through the same plots. |
| FR-REC-3 | D | Demodulation / measurement plugins. |

---

## 6. Non-functional requirements

| ID | Pri | Requirement |
| --- | --- | --- |
| NFR-1 | M | UI toolkit: PyQt6 + pyqtgraph (not matplotlib for the live waterfall). |
| NFR-2 | M | Language: Python 3.10+. |
| NFR-3 | M | Hardware driver: UHD Python API; `uhd` is an optional extra (`[hardware]`). |
| NFR-4 | M | Mock mode shall run without a radio so UI/DSP can be developed offline. |
| NFR-5 | M | Device access is serialized on one worker thread (UHD is not treated as freely multi-threaded). |
| NFR-6 | M | Prototype is not required to sustain rates near 56 MHz USB throughput. |
| NFR-7 | D | Documented install of matching UHD C++ and Python versions on Windows. |
| NFR-8 | D | Automated tests beyond mock DSP/worker smoke. |
| NFR-9 | D | Accessibility, localization, and installer packaging. |

---

## 7. User interface requirements

| ID | Pri | Requirement |
| --- | --- | --- |
| UI-1 | M | Left: device + RX controls + status. Right: spectrum, waterfall, time plots. |
| UI-2 | M | Controls: source (Mock / Hardware), UHD args, Connect, Disconnect, Apply tune, Start RX, Stop RX. |
| UI-3 | M | Window title identifies the product (USRP B205mini-i RX Monitor). |
| UI-4 | M | Closing the window shall stop the worker and release the device. |

---

## 8. Data and interfaces

| ID | Requirement |
| --- | --- |
| IF-1 | Host↔radio: USB via UHD stream args CPU `fc32`, wire `sc16`. |
| IF-2 | IQ in the ring buffer: `numpy.complex64`. |
| IF-3 | No network protocol in the prototype. |

---

## 9. Safety and operational notes

- Never apply more than −15 dBm into an RX port.
- Loopback requires ≥ 30 dB attenuation.
- TX (if added) must not run into an open SMA.
- Custom FPGA images must match the installed UHD FPGA compatibility number.

---

## 10. Traceability (prototype implementation)

| Area | Module |
| --- | --- |
| Device backends | `src/usrp_monitor/device.py` |
| Worker / ring buffer | `src/usrp_monitor/rx_worker.py` |
| FFT / power | `src/usrp_monitor/dsp.py` |
| UI | `src/usrp_monitor/ui.py` |
| Entry | `src/usrp_monitor/__main__.py` |

---

## 11. Open points (to fill in later)

- [ ] Target UHD version pin (e.g. 4.9.x)
- [ ] Whether TX is controls-only or includes sample streaming
- [ ] Whether image load is args-only or a file dialog + reconnect wizard
- [ ] Maximum supported sample rate on USB 3.0 for this app
- [ ] Calibration / power API
- [ ] GPIO and user FPGA registers

---

## 12. Document history

| Version | Status | Notes |
| --- | --- | --- |
| 0.1.0-draft | Draft | Baseline from prototype (RX monitor + mock). Future TX/images/recording IDs reserved. |
