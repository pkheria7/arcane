from __future__ import annotations

from .types import GpsReading


def _nmea_to_decimal(value: str, hemisphere: str) -> float | None:
    if not value:
        return None
    dot = value.find(".")
    degree_digits = dot - 2
    degrees = float(value[:degree_digits])
    minutes = float(value[degree_digits:])
    decimal = degrees + minutes / 60.0
    return -decimal if hemisphere in {"S", "W"} else decimal


class GpsReader:
    def read(self) -> GpsReading: ...


class NullGpsReader(GpsReader):
    def read(self) -> GpsReading:
        return GpsReading()


class SerialGpsReader(GpsReader):
    def __init__(self, port: str = "/dev/serial0", baudrate: int = 9600, timeout: float = 0.05) -> None:
        import serial

        self.serial = serial.Serial(port, baudrate=baudrate, timeout=timeout)

    def read(self) -> GpsReading:
        for _ in range(8):
            line = self.serial.readline().decode("ascii", errors="ignore").strip()
            if line.startswith("$GPGGA") or line.startswith("$GNGGA"):
                parts = line.split(",")
                if len(parts) > 6:
                    lat = _nmea_to_decimal(parts[2], parts[3])
                    lon = _nmea_to_decimal(parts[4], parts[5])
                    return GpsReading(lat=lat, lon=lon, fix_quality=int(parts[6] or 0))
        return GpsReading()
