"""Com of the Teensy (com.cpp), compiled on a PC with a fake Arduino.h."""

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from dvb_usb_com.framing import FrameDecoder, encode_frame

CPP_DIR = Path(__file__).parents[1] / "cpp"

NACK = b"\x7f"
UNKNOWN = b"\xff"

ARDUINO_H = r"""
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <vector>
typedef uint8_t byte;
struct Stream {
    std::vector<uint8_t> in, out;
    size_t next = 0;
    int available() { return in.size() - next; }
    int read() { return in[next++]; }
    size_t write(const uint8_t* data, size_t size) {
        out.insert(out.end(), data, data + size);
        return size;
    }
    void flush() {}
    void begin(uint32_t) {}
};
struct usb_serial_class : Stream {};
struct HardwareSerial : Stream {};
"""

# id 1 is echoed with its size, id 2 prints a text; stdin and stdout in hex
HARNESS = r"""
#include <com.h>
#include <stdio.h>

HardwareSerial stream;
Com com(&stream, 115200);

void echo(byte* msg, byte size) {
    byte answer[256];
    memcpy(answer, msg, size);
    answer[0] = 200;
    com.send_msg(answer, size);
}

void print_on(byte* msg, byte size) {
    com.print_enabled = msg[1];
    char text[] = "hello";
    com.print(text);
}

void (*callbacks[256])(byte* msg, byte size);

int main() {
    callbacks[1] = &echo;
    callbacks[2] = &print_on;
    unsigned int value;
    while (scanf("%2x", &value) == 1) {
        stream.in.push_back(value);
    }
    while (stream.available()) {
        com.handle_callback(callbacks);
    }
    for (uint8_t data : stream.out) {
        printf("%02x", data);
    }
    return 0;
}
"""

type Teensy = Callable[[bytes], list[bytes]]


@pytest.fixture(scope="module")
def teensy(tmp_path_factory: pytest.TempPathFactory) -> Teensy:
    """Gives bytes to Com and returns the messages it answered."""
    compiler = shutil.which("g++")
    if compiler is None:
        if os.environ.get("CI"):
            pytest.fail("g++ is required in CI for the protocol tests")
        pytest.skip("g++ not found: C++ protocol tests skipped")

    build = tmp_path_factory.mktemp("com_cpp")
    (build / "Arduino.h").write_text(ARDUINO_H, encoding="utf-8")
    (build / "harness.cpp").write_text(HARNESS, encoding="utf-8")
    binary = build / "harness"
    subprocess.run(
        [
            compiler,
            "-std=c++17",
            "-Wall",
            "-DARDUINO=1",
            f"-I{build}",
            f"-I{CPP_DIR / 'include'}",
            str(build / "harness.cpp"),
            str(CPP_DIR / "src" / "com.cpp"),
            str(CPP_DIR / "src" / "codec.cpp"),
            "-o",
            str(binary),
        ],
        check=True,
        capture_output=True,
    )

    def run(data: bytes) -> list[bytes]:
        result = subprocess.run(
            [str(binary)], input=data.hex(), check=True, capture_output=True, text=True
        )
        decoder = FrameDecoder()
        messages = decoder.feed(bytes.fromhex(result.stdout))
        assert decoder.errors == 0
        return messages

    return run


def damaged(message: bytes) -> bytes:
    frame = bytearray(encode_frame(message))
    frame[-2] ^= 0x01 if frame[-2] != 0x01 else 0x02  # never a 0x00
    return bytes(frame)


@pytest.mark.parametrize("size", [1, 2, 100, 253, 254, 255])
def test_message_reaches_its_callback(teensy: Teensy, size: int) -> None:
    payload = bytes(i % 256 for i in range(size - 1))
    assert teensy(encode_frame(b"\x01" + payload)) == [b"\xc8" + payload]


def test_old_signature_in_the_data_is_harmless(teensy: Teensy) -> None:
    payload = b"\xba\xdd\x1c\xc5\x00\xba\xdd\x1c\xc5"
    assert teensy(encode_frame(b"\x01" + payload)) == [b"\xc8" + payload]


def test_damaged_frame_then_valid_one(teensy: Teensy) -> None:
    data = damaged(b"\x01abc") + encode_frame(b"\x01def")
    assert teensy(data) == [NACK, b"\xc8def"]


def test_oversized_frame_then_valid_one(teensy: Teensy) -> None:
    data = b"\x05" * 1000 + b"\x00" + encode_frame(b"\x01def")
    assert teensy(data) == [NACK, b"\xc8def"]


def test_unknown_message(teensy: Teensy) -> None:
    assert teensy(encode_frame(b"\x09")) == [UNKNOWN + b"\x09"]


def test_every_nack_resends_the_same_message(teensy: Teensy) -> None:
    data = encode_frame(b"\x01abc") + 3 * encode_frame(NACK)
    assert teensy(data) == 4 * [b"\xc8abc"]


def test_sent_nack_does_not_replace_the_last_message(teensy: Teensy) -> None:
    data = encode_frame(b"\x01abc") + damaged(b"\x01def") + encode_frame(NACK)
    assert teensy(data) == [b"\xc8abc", NACK, b"\xc8abc"]


def test_nack_before_any_message_sends_nothing(teensy: Teensy) -> None:
    assert teensy(encode_frame(NACK)) == []


def test_print_can_be_turned_off(teensy: Teensy) -> None:
    assert teensy(encode_frame(b"\x02\x01")) == [b"\xfehello"]
    assert teensy(encode_frame(b"\x02\x00")) == []
