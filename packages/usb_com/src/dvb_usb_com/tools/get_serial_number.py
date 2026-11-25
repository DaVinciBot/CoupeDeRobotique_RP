"""Utilities to list serial numbers of connected devices."""

from __future__ import annotations

import logging

import serial.tools.list_ports

_logger = logging.getLogger(__name__)


def get_all_serial_number() -> None:
    """Print the serial numbers of all detected serial ports."""
    ports = serial.tools.list_ports.comports()
    _logger.info(f"[USB_COM] Number of ports: {len(ports)}")
    for port in ports:
        _logger.info(f"[USB_COM] Serial Number: {port.serial_number}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    get_all_serial_number()
