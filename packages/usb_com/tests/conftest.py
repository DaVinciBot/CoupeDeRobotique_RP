"""Builds a small C++ program around codec.cpp and messages.h.

The protocol tests use it to check that the C++ and Python sides agree. It
needs g++: without it the tests are skipped on a PC, but they fail in CI.
"""

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

CPP_DIR = Path(__file__).parents[1] / "cpp"
MESSAGES_H = CPP_DIR / "include" / "messages.h"

HARNESS = r"""
#include <codec.h>
#include <messages.h>
#include <stdio.h>
#include <string.h>
#include <string>
#include <vector>

static std::vector<uint8_t> parse_hex(const std::string& line) {
    std::vector<uint8_t> out;
    for (size_t i = 0; i + 1 < line.size(); i += 2) {
        out.push_back((uint8_t)std::stoi(line.substr(i, 2), nullptr, 16));
    }
    return out;
}

static void print_hex(const uint8_t* data, size_t size) {
    for (size_t i = 0; i < size; i++) {
        printf("%02x", data[i]);
    }
    printf("\n");
}

int main(int argc, char** argv) {
    if (argc > 1 && strcmp(argv[1], "sizes") == 0) {
        @SIZES@
        return 0;
    }
    bool encode = argc > 1 && strcmp(argv[1], "encode") == 0;
    char buffer[4096];
    while (fgets(buffer, sizeof(buffer), stdin) != nullptr) {
        std::string line(buffer);
        while (!line.empty() && (line.back() == '\n' || line.back() == '\r')) {
            line.pop_back();
        }
        std::vector<uint8_t> in = parse_hex(line);
        if (encode) {
            uint8_t frame[usb_com::MAX_FRAME_SIZE];
            size_t size = usb_com::encode_frame(in.data(), in.size(), frame);
            print_hex(frame, size);
        } else {
            uint8_t msg[usb_com::MAX_MSG_SIZE];
            size_t size = usb_com::decode_frame(in.data(), in.size(), msg);
            if (size == 0) {
                printf("ERR\n");
            } else {
                print_hex(msg, size);
            }
        }
        fflush(stdout);
    }
    return 0;
}
"""

type CppTool = Callable[[str, list[str]], list[str]]


def message_struct_names() -> list[str]:
    """Names of the message structures declared in messages.h."""
    return re.findall(r"^struct (msg_\w+)", MESSAGES_H.read_text(encoding="utf-8"), re.M)


@pytest.fixture(scope="session")
def cpp_tool(tmp_path_factory: pytest.TempPathFactory) -> CppTool:
    """Runs the C++ harness: mode 'encode', 'decode' or 'sizes', one line per input."""
    compiler = shutil.which("g++")
    if compiler is None:
        if os.environ.get("CI"):
            pytest.fail("g++ is required in CI for the protocol tests")
        pytest.skip("g++ not found: C++ protocol tests skipped")

    sizes = "\n".join(
        f'printf("{name} %d %zu\\n", (int){name}().command, sizeof({name}));'
        for name in message_struct_names()
    )
    build = tmp_path_factory.mktemp("usb_com_cpp")
    source = build / "harness.cpp"
    source.write_text(HARNESS.replace("@SIZES@", sizes), encoding="utf-8")
    binary = build / "harness"
    subprocess.run(
        [
            compiler,
            "-std=c++17",
            "-Wall",
            "-Werror",
            f"-I{CPP_DIR / 'include'}",
            str(source),
            str(CPP_DIR / "src" / "codec.cpp"),
            "-o",
            str(binary),
        ],
        check=True,
        capture_output=True,
    )

    def run(mode: str, lines: list[str]) -> list[str]:
        result = subprocess.run(
            [str(binary), mode],
            input="".join(f"{line}\n" for line in lines),
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.splitlines()

    return run
