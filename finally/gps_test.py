from __future__ import annotations

import argparse
from time import monotonic


def nmea_to_decimal(value: str, hemisphere: str) -> float | None:
    if not value:
        return None
    dot = value.find(".")
    degree_digits = dot - 2
    degrees = float(value[:degree_digits])
    minutes = float(value[degree_digits:])
    decimal = degrees + minutes / 60.0
    return -decimal if hemisphere in {"S", "W"} else decimal


def decode_gga(line: str) -> str | None:
    if not (line.startswith("$GPGGA") or line.startswith("$GNGGA")):
        return None
    parts = line.split(",")
    if len(parts) <= 6:
        return "GGA malformed"
    lat = nmea_to_decimal(parts[2], parts[3])
    lon = nmea_to_decimal(parts[4], parts[5])
    fix = int(parts[6] or 0)
    sats = parts[7] if len(parts) > 7 else ""
    return f"GGA fix={fix} sats={sats or '?'} lat={lat} lon={lon}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Print raw GPS NMEA data from the Pi UART.")
    parser.add_argument("--port", default="/dev/serial0")
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument("--seconds", type=float, default=30.0)
    args = parser.parse_args()

    import serial

    print(f"Reading GPS from {args.port} at {args.baudrate} baud for {args.seconds:.0f}s.")
    print("You should see raw $GP.../$GN... lines. GGA fix=0 means no satellite fix yet.")
    deadline = monotonic() + args.seconds
    with serial.Serial(args.port, baudrate=args.baudrate, timeout=1.0) as ser:
        while monotonic() < deadline:
            line = ser.readline().decode("ascii", errors="ignore").strip()
            if not line:
                print("(no data)")
                continue
            decoded = decode_gga(line)
            print(line)
            if decoded:
                print("  " + decoded)


if __name__ == "__main__":
    main()
