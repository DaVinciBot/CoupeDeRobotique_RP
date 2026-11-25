"""USB communication helper with CRC and dummy mode."""

from __future__ import annotations

import threading
import time
from functools import wraps
from typing import TYPE_CHECKING, Any

from serial import Serial
from serial.tools.list_ports import comports

from dvb_usb_com.com.dummy import DummySerial
from dvb_usb_com.com.exceptions import ComError
from dvb_usb_com.framing import DELIMITER, FrameError, decode_frame, encode_frame
from dvb_usb_com.messages import Messages

NACK_ID = 127

if TYPE_CHECKING:
    from collections.abc import Callable
    from logging import Logger


class Com:
    """Handle USB exchanges with a Teensy microcontroller.

    Supports message transmission, CRC-16 verification, and callback mechanisms.
    Messages can be sent from several threads; callbacks run in the receiver thread.
    """

    def __init__(
        self,
        logger: Logger,
        serial_number: int,
        vid: int,
        pid: int,
        baudrate: int,
        *,
        enable_crc: bool = True,
        enable_dummy: bool = False,
    ) -> None:
        """Initialize the USB communication instance.

        Args:
            logger (Logger): Logger instance for logging messages.
            serial_number (int): Serial number of the target device.
            vid (int): Vendor ID of the USB device.
            pid (int): Product ID of the USB device.
            baudrate (int): Baud rate for serial communication.
            enable_crc (bool, optional):
                Checks the CRC-16 of the received messages. Defaults to ``True``.
                The sent messages always have one: the Teensy requires it.
            enable_dummy (bool, optional):
                Enables dummy mode for testing. Defaults to ``False``.
        """
        # Initialize init variables
        self._logger: Logger = logger
        self.serial_number: int = serial_number
        self.vid: int = vid
        self.pid: int = pid
        self.baudrate: int = baudrate
        self.enable_crc: bool = enable_crc
        self.enable_dummy: bool = enable_dummy

        # Initialize usb com variables
        self._device: Serial | DummySerial = self._get_serial()
        # One writer at a time: the receiver thread also sends (NACK, retransmission)
        self._write_lock = threading.RLock()

        self.last_message: bytes | None = None
        self.message_id_callback: dict[int, Callable[[bytes], None]] = {}

        # Start the receiver thread (if not in dummy mode),
        # it is responsible for handling the received data
        self._receiver_thread: threading.Thread | None = self._start_receiver()

    # region ======= Private methods =======
    def _get_serial(self) -> Serial | DummySerial:
        """Detect and initialize the serial device or dummy mode.

        Returns:
            Serial | DummySerial:
                Initialized serial connection or dummy instance.

        Raises:
            ComError: If no device is found and dummy mode is disabled.
        """
        device_found: Serial | DummySerial | None = None

        for port in comports():
            if (
                port.vid == self.vid
                and port.pid == self.pid
                and port.serial_number is not None
                and port.serial_number == str(self.serial_number)
            ):
                device_found = Serial(port.device, baudrate=self.baudrate)
                break

        if device_found is None:
            if self.enable_dummy:
                self._logger.info("[USB_COM] Dummy mode enabled")
                device_found = DummySerial()
            else:
                msg = "[USB_COM] No device found"
                self._logger.critical(msg)
                raise ComError(msg)

        return device_found

    def _start_receiver(self) -> threading.Thread | None:
        """Starts the receiver thread unless in dummy mode.

        Returns:
            threading.Thread | None: Receiver thread or None if dummy mode is enabled.
        """
        # If in dummy mode, do not start the receiver thread
        if self.enable_dummy:
            return None

        receiver = threading.Thread(target=self.__receiver, name="USBComReceiver")
        receiver.start()
        return receiver

    def __receiver(self) -> None:
        """Run in a thread and dispatch messages based on the protocol format.

        Format: ``msg_type | msg_data | msg_length | CRC16``, then COBS and ``0x00``
        (see framing.py).
        """
        while True:
            try:
                frame = self.read_bytes().removesuffix(DELIMITER)
                if not frame:
                    continue

                try:
                    msg = decode_frame(frame, check_crc=self.enable_crc)
                except FrameError as e:
                    self._logger.warning(f"[USB_COM] Invalid frame, sending NACK [{e}]")
                    self.send_bytes(Messages.NACK.to_bytes())  # send NACK
                    continue

                try:
                    if msg[0] == NACK_ID:
                        self._logger.warning("[USB_COM] Received NACK")
                        with self._write_lock:
                            if self.last_message is not None:
                                self.send_bytes(self.last_message)
                                self._logger.info(
                                    f"[USB_COM] Resending message: {self.last_message[0]}",
                                )
                                self.last_message = None
                    else:
                        self.message_id_callback.get(
                            msg[0],
                            lambda x: self._logger.error(
                                f"[USB_COM] Unknown message type: {x}",
                            ),
                        )(msg[1:])

                except Exception as e:
                    self._logger.error(f"[USB_COM] Message handling crashed: {e}")
                    time.sleep(0.5)  # Wait to avoid spamming the logs

            except Exception as e:
                self._logger.critical(
                    f"[USB_COM] Connection closed, Teensy crashed? [{e}]",
                )
                time.sleep(0.5)  # Wait to avoid spamming the logs

    # endregion

    # region ======= Public methods =======
    @staticmethod
    def check_dummy(func: Callable[..., Any]) -> Callable[..., Any]:  # UNUSED
        """Decorator to cancel execution when in dummy mode.

        Args:
            func (Callable[..., Any]): Function to wrap.

        Returns:
            Callable[..., Any]:
                Wrapped function that returns ``None`` if dummy mode is enabled.
        """

        @wraps(func)
        def wrapper(  # UNUSED
            self: Com,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            # Check if the self.enable_dummy attribute is disabled (False)
            if self.enable_dummy:
                self._logger.debug(f"[USB_COM:Dummy] {func.__name__} called")
                return None  # Prevents the function from executing

            # Execute the function normally
            return func(self, *args, **kwargs)

        return wrapper

    def send_bytes(self, data: bytes) -> None:
        """Sends bytes over the serial connection.

        Args:
            data (bytes): Data to be transmitted.
        """
        frame = encode_frame(data)
        with self._write_lock:
            # A NACK is not kept: the Teensy would ask for it again instead of the lost message
            if data[0] != NACK_ID:
                self.last_message = data

            self._device.reset_output_buffer()
            self._device.write(frame)
            while self._device.out_waiting:
                pass

    def read_bytes(self) -> bytes:
        """Reads bytes from the serial connection until the end of a frame (``0x00``).

        Returns:
            bytes: Received data.
        """
        return self._device.read_until(DELIMITER)

    def add_callback(self, func: Callable[[bytes], None], iid: int) -> None:
        """Registers a callback for a specific message ID.

        Args:
            func (Callable[[bytes], None]): Callback function.
            iid (int): Message ID to associate with the callback.
        """
        if self.message_id_callback.get(iid) is not None:
            self._logger.warning(
                f"[USB_COM] Callback for message ID {iid} already exists",
            )

        self.message_id_callback[iid] = func

    # endregion
