import random
from collections.abc import Callable

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dvb_usb_com.framing import (
    MAX_FRAME_SIZE,
    MAX_MSG_SIZE,
    FrameDecoder,
    FrameError,
    cobs_decode,
    cobs_encode,
    crc16,
    decode_frame,
    encode_frame,
)

type CppTool = Callable[[str, list[str]], list[str]]

messages = st.binary(min_size=1, max_size=MAX_MSG_SIZE)


def test_crc16_is_ccitt_false() -> None:
    # check value of CRC-16/CCITT-FALSE
    assert crc16(b"123456789") == 0x29B1


@pytest.mark.parametrize(
    ("data", "encoded"),
    [
        (b"\x00", b"\x01\x01"),
        (b"\x00\x00", b"\x01\x01\x01"),
        (b"\x11\x22\x00\x33", b"\x03\x11\x22\x02\x33"),
        (b"\x11\x22\x33\x44", b"\x05\x11\x22\x33\x44"),
        (b"\x11\x00\x00\x00", b"\x02\x11\x01\x01\x01"),
    ],
)
def test_cobs_known_vectors(data: bytes, encoded: bytes) -> None:
    assert cobs_encode(data) == encoded
    assert cobs_decode(encoded) == data


@given(st.binary(max_size=1000))
def test_cobs_round_trip_without_zero(data: bytes) -> None:
    encoded = cobs_encode(data)
    assert 0 not in encoded
    assert cobs_decode(encoded) == data


@given(messages)
def test_frame_round_trip(msg: bytes) -> None:
    frame = encode_frame(msg)
    assert frame[-1] == 0
    assert 0 not in frame[:-1]
    assert len(frame) <= MAX_FRAME_SIZE
    assert decode_frame(frame[:-1]) == msg


def test_frame_size_limits() -> None:
    with pytest.raises(ValueError, match="message size"):
        encode_frame(b"")
    with pytest.raises(ValueError, match="message size"):
        encode_frame(bytes(MAX_MSG_SIZE + 1))


@given(messages, st.data())
def test_any_single_bit_error_is_detected(msg: bytes, data: st.DataObject) -> None:
    frame = bytearray(encode_frame(msg)[:-1])
    index = data.draw(st.integers(0, len(frame) - 1))
    frame[index] ^= 1 << data.draw(st.integers(0, 7))
    # a byte turned into 0x00 would cut the frame in two: the decoder sees it
    if frame[index] == 0:
        decoder = FrameDecoder()
        assert decoder.feed(bytes(frame) + b"\x00") == []
        return
    with pytest.raises(FrameError):
        decode_frame(bytes(frame))


@given(messages, st.data())
def test_truncated_frame_is_rejected(msg: bytes, data: st.DataObject) -> None:
    frame = encode_frame(msg)[:-1]
    cut = data.draw(st.integers(0, len(frame) - 1))
    decoder = FrameDecoder()
    assert decoder.feed(frame[:cut] + b"\x00") == []


@given(st.lists(messages, min_size=1, max_size=10), st.binary(max_size=50))
def test_decoder_resynchronizes_after_garbage(msgs: list[bytes], garbage: bytes) -> None:
    # garbage before the first frame, as when the link starts in the middle
    stream = garbage + b"\x00" + b"".join(encode_frame(msg) for msg in msgs)
    decoder = FrameDecoder()
    received: list[bytes] = []
    # bytes arrive in small random chunks
    for start in range(0, len(stream), 7):
        received += decoder.feed(stream[start : start + 7])
    assert received == msgs


def test_decoder_drops_oversized_frame() -> None:
    decoder = FrameDecoder()
    assert decoder.feed(b"\x01" * (MAX_FRAME_SIZE + 10) + b"\x00") == []
    assert decoder.errors == 1
    assert decoder.feed(encode_frame(b"\x80\x01")) == [b"\x80\x01"]


def random_messages(count: int) -> list[bytes]:
    """Messages of every size, with many 0x00 and 0xFF to stress COBS."""
    rng = random.Random(2027)
    msgs = [
        bytes(rng.choice([0, 0xFF, rng.randrange(256)]) for _ in range(size))
        for size in (1, 253, 254, 255)
    ]
    msgs += [rng.randbytes(rng.randint(1, MAX_MSG_SIZE)) for _ in range(count)]
    return msgs


def test_cpp_encodes_like_python(cpp_tool: CppTool) -> None:
    msgs = random_messages(300)
    assert cpp_tool("encode", [msg.hex() for msg in msgs]) == [
        encode_frame(msg).hex() for msg in msgs
    ]


def test_cpp_decodes_python_frames(cpp_tool: CppTool) -> None:
    msgs = random_messages(300)
    decoded = cpp_tool("decode", [encode_frame(msg)[:-1].hex() for msg in msgs])
    assert decoded == [msg.hex() for msg in msgs]


def test_cpp_rejects_damaged_frames(cpp_tool: CppTool) -> None:
    rng = random.Random(2028)
    lines: list[str] = []
    for msg in random_messages(300):
        frame = bytearray(encode_frame(msg)[:-1])
        # one flipped bit; a byte turned into 0x00 is cut by the stream reader instead
        index = rng.randrange(len(frame))
        frame[index] ^= 1 << rng.randrange(8)
        if frame[index] != 0:
            lines.append(frame.hex())
        # truncated frame
        lines.append(frame[: rng.randrange(1, len(frame))].hex())
    assert cpp_tool("decode", lines) == ["ERR"] * len(lines)
