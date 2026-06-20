from __future__ import annotations

from .system_packages import add_system_dist_packages


class GpioFactoryError(RuntimeError):
    pass


def configure_gpiozero_pin_factory(preferred: str = "auto") -> str:
    """Configure gpiozero with a concrete pin factory.

    Raspberry Pi OS and Python virtual environments often hide the system GPIO
    packages from gpiozero's default discovery. This makes startup deterministic
    and produces an actionable error when the Pi is missing permissions/packages.
    """
    add_system_dist_packages()
    from gpiozero import Device

    if Device.pin_factory is not None:
        return Device.pin_factory.__class__.__name__

    candidates = [preferred] if preferred != "auto" else ["lgpio", "rpigpio", "native", "pigpio"]
    errors: list[str] = []
    for candidate in candidates:
        try:
            if candidate == "lgpio":
                from gpiozero.pins.lgpio import LGPIOFactory

                Device.pin_factory = LGPIOFactory()
            elif candidate == "pigpio":
                from gpiozero.pins.pigpio import PiGPIOFactory

                Device.pin_factory = PiGPIOFactory()
            elif candidate == "rpigpio":
                from gpiozero.pins.rpigpio import RPiGPIOFactory

                Device.pin_factory = RPiGPIOFactory()
            elif candidate == "native":
                from gpiozero.pins.native import NativeFactory

                Device.pin_factory = NativeFactory()
            else:
                errors.append(f"{candidate}: unknown pin factory")
                continue
            return Device.pin_factory.__class__.__name__
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")

    raise GpioFactoryError(
        "Unable to configure GPIO access. Tried: "
        + "; ".join(errors)
        + "\nFix on the Raspberry Pi:\n"
        + "  sudo apt update\n"
        + "  sudo apt install -y python3-lgpio python3-rpi-lgpio\n"
        + "  sudo usermod -aG gpio,video,i2c,dialout $USER\n"
        + "  sudo reboot\n"
        + "Then inside the venv:\n"
        + "  pip install gpiozero smbus2 pyserial\n"
        + "If you need a quick permission check, run once with sudo."
    )
