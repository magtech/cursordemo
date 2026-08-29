"""Launch the RX monitor GUI."""

from __future__ import annotations

import argparse
import sys

from usrp_monitor.device import uhd_available


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="USRP B205mini-i RX monitor")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--mock",
        action="store_true",
        help="Use the simulated radio (no UHD / no hardware).",
    )
    group.add_argument(
        "--hardware",
        action="store_true",
        help="Require a real USRP via UHD (fail if uhd is missing).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    prefer_mock = bool(args.mock)
    force_hardware = bool(args.hardware)
    if not prefer_mock and not force_hardware and not uhd_available():
        prefer_mock = True
        print("uhd is not importable; starting in mock mode (pass --hardware to require UHD).")

    if force_hardware and not uhd_available():
        print("error: --hardware was set but the uhd package could not be imported.", file=sys.stderr)
        return 1

    from PyQt6.QtWidgets import QApplication

    from usrp_monitor.ui import MonitorWindow

    app = QApplication(sys.argv)
    window = MonitorWindow(prefer_mock=prefer_mock, force_hardware=force_hardware)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
