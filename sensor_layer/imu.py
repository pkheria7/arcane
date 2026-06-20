from __future__ import annotations

import math
from time import time

from .types import ImuReading

MPU6050_ADDR = 0x68
PWR_MGMT_1 = 0x6B
ACCEL_XOUT_H = 0x3B
GYRO_ZOUT_H = 0x47


class ImuReader:
    def read(self) -> ImuReading: ...


class NullImuReader(ImuReader):
    def read(self) -> ImuReading:
        return ImuReading()


class Mpu6050Reader(ImuReader):
    def __init__(self, bus_id: int = 1, address: int = MPU6050_ADDR) -> None:
        from smbus2 import SMBus

        self.bus = SMBus(bus_id)
        self.address = address
        self.bus.write_byte_data(address, PWR_MGMT_1, 0)
        self.heading = 0.0
        self.last_time = time()

    def _read_word(self, register: int) -> int:
        high = self.bus.read_byte_data(self.address, register)
        low = self.bus.read_byte_data(self.address, register + 1)
        value = (high << 8) + low
        return value - 65536 if value >= 0x8000 else value

    def read(self) -> ImuReading:
        ax = self._read_word(ACCEL_XOUT_H) / 16384.0
        ay = self._read_word(ACCEL_XOUT_H + 2) / 16384.0
        az = self._read_word(ACCEL_XOUT_H + 4) / 16384.0
        gyro_z = self._read_word(GYRO_ZOUT_H) / 131.0
        now = time()
        dt = max(0.0, now - self.last_time)
        self.last_time = now
        self.heading = (self.heading + gyro_z * dt) % 360.0
        acceleration = math.sqrt(ax * ax + ay * ay + az * az)
        return ImuReading(heading=self.heading, acceleration=acceleration, accel_x=ax, accel_y=ay, accel_z=az, gyro_z=gyro_z)
