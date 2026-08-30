# USRP B205mini-i RX Monitor

Desktop prototype that connects to an Ettus **USRP B205mini-i** (UHD `type=b200`) and shows live RX spectrum, waterfall, and I/Q time-domain samples. A mock radio is included so the UI can run without hardware.

## Requirements

- Python 3.10 or newer (3.10/3.12 recommended if you need the official UHD wheels; other versions can still run mock mode)
- Windows (tested target): USB 3.0 recommended
- For a real radio: Ettus/NI **UHD** installed first, then a matching `uhd` Python package

### Windows UHD (hardware)

1. Install the USRP Hardware Driver from Ettus/NI (for example UHD 4.9+).
2. Confirm the driver sees the device:

   ```text
   uhd_find_devices
   uhd_config_info --print-all
   ```

3. Install the **same** UHD version into Python (the numeric version from `uhd_config_info`):

   ```text
   py -3.12 -m pip install uhd==<version>
   ```

   Mismatched UHD C++ vs Python wheels will fail to import or open the device.

4. Prefer a USB 3.0 port. The prototype defaults to **2 Msps**, which is usually fine on USB 2.0; higher rates are not.

5. Connect an antenna to **RX2** or **TX/RX** and select that port in the UI.

Python `uhd` is optional at install time (`pip install -e ".[hardware]"`). If `uhd` is missing, the app falls back to mock mode.

## Install and run

```text
py -3.12 -m pip install -e .
py -3.12 -m usrp_monitor
```

- Default: try UHD; if import or connect is unavailable, use the mock device.
- Force mock: `py -3.12 -m usrp_monitor --mock`
- Force hardware: `py -3.12 -m usrp_monitor --hardware`

Defaults: 100 MHz center, 2 Msps, mid-range RX gain.

## Prototype scope

Receive-only monitor. No TX, no IQ recording, no demodulation.
