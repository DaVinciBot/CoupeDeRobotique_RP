"""Framing of the Pi <-> Teensy messages, identical to codec.cpp.

Frame: ``[msg_id u8][payload N][len u8][crc16 u16 LE]`` -> COBS -> ``0x00``.
See docs/adr/0003-motion-protocol.md.
"""

import binascii
from dataclasses import dataclass, field

MAX_MSG_SIZE = 255
MAX_RAW_SIZE = MAX_MSG_SIZE + 3
MAX_FRAME_SIZE = MAX_RAW_SIZE + (MAX_RAW_SIZE + 253) // 254 + 1
DELIMITER = b"\x00"


class FrameError(ValueError):
    """A frame that is not valid COBS, or whose length or CRC is wrong."""


def crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection."""
    return binascii.crc_hqx(data, 0xFFFF)


def cobs_encode(data: bytes) -> bytes:
    """COBS encoding, byte for byte the same as codec.cpp."""
    out = bytearray([0])
    code_index = 0
    code = 1
    for byte in data:
        if byte == 0:
            out[code_index] = code
            code_index = len(out)
            out.append(0)
            code = 1
            continue
        out.append(byte)
        code += 1
        if code == 0xFF:
            out[code_index] = code
            code_index = len(out)
            out.append(0)
            code = 1
    out[code_index] = code
    return bytes(out)


def cobs_decode(data: bytes) -> bytes:
    """COBS decoding; raises FrameError if the input is not valid COBS."""
    out = bytearray()
    index = 0
    while index < len(data):
        code = data[index]
        index += 1
        if code == 0 or index + code - 1 > len(data):
            raise FrameError("invalid COBS block")
        out += data[index : index + code - 1]
        index += code - 1
        if code != 0xFF and index < len(data):
            out.append(0)
    return bytes(out)


def encode_frame(msg: bytes) -> bytes:
    """Frame of a message (id included), 0x00 delimiter included."""
    if not 1 <= len(msg) <= MAX_MSG_SIZE:
        raise ValueError(f"message size must be 1 to {MAX_MSG_SIZE}, got {len(msg)}")
    raw = msg + bytes([len(msg)])
    raw += crc16(raw).to_bytes(2, "little")
    return cobs_encode(raw) + DELIMITER


def decode_frame(frame: bytes, *, check_crc: bool = True) -> bytes:
    """Message of a frame given without its 0x00 delimiter."""
    raw = cobs_decode(frame)
    if len(raw) < 4:
        raise FrameError(f"frame too short: {len(raw)} bytes")
    msg, size, crc = raw[:-3], raw[-3], int.from_bytes(raw[-2:], "little")
    if size != len(msg):
        raise FrameError(f"length field {size} does not match message size {len(msg)}")
    if check_crc and crc != crc16(raw[:-2]):
        raise FrameError("CRC mismatch")
    return msg


@dataclass(slots=True)
class FrameDecoder:
    """Cuts a byte stream into messages; damaged frames are counted and dropped."""

    errors: int = 0
    _buffer: bytearray = field(default_factory=bytearray)
    _overflow: bool = False

    def feed(self, data: bytes) -> list[bytes]:
        """Messages completed by these bytes, in order."""
        messages: list[bytes] = []
        for byte in data:
            if byte != 0:
                # a frame longer than the largest one cannot be valid
                if len(self._buffer) >= MAX_FRAME_SIZE - 1:
                    self._overflow = True
                else:
                    self._buffer.append(byte)
                continue
            frame = bytes(self._buffer)
            overflow = self._overflow
            self._buffer.clear()
            self._overflow = False
            if overflow:
                self.errors += 1
                continue
            if not frame:
                continue
            try:
                messages.append(decode_frame(frame))
            except FrameError:
                self.errors += 1
        return messages
