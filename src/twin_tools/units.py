"""The units a quantity in the AR4 kDB may use: each unit's kind and its factor to SI."""

from __future__ import annotations

import math

DEG = math.pi / 180

# unit: (kind, factor that converts a value in this unit to the SI unit of its kind)
UNITS: dict[str, tuple[str, float]] = {
    "rad": ("angle", 1.0),
    "deg": ("angle", DEG),
    "rad/s": ("angular speed", 1.0),
    "deg/s": ("angular speed", DEG),
    "rpm": ("angular speed", 2 * math.pi / 60),
    "N m": ("torque", 1.0),
    "N cm": ("torque", 0.01),
    "kg cm": ("torque", 0.0980665),  # kilogram-force centimetre, common in stepper datasheets
    "N": ("force", 1.0),
    "kg": ("mass", 1.0),
    "g": ("mass", 1e-3),
    "m": ("length", 1.0),
    "mm": ("length", 1e-3),
    "m/s": ("speed", 1.0),
    "mm/s": ("speed", 1e-3),
    "mm^3": ("volume", 1e-9),
    "cm^3": ("volume", 1e-6),
    "m^3": ("volume", 1.0),
    "kg/m^3": ("density", 1.0),
    "g/cm^3": ("density", 1000.0),
    "kg m^2": ("inertia", 1.0),
    "g cm^2": ("inertia", 1e-7),
    "A": ("current", 1.0),
    "V": ("voltage", 1.0),
    "W": ("power", 1.0),
    "s": ("time", 1.0),
    "us": ("time", 1e-6),
    "1": ("ratio", 1.0),
}


def kind(unit: str) -> str | None:
    return UNITS[unit][0] if unit in UNITS else None


def to_si(value: float, unit: str) -> float:
    return value * UNITS[unit][1]
