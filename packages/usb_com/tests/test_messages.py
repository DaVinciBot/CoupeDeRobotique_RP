import re
from collections.abc import Callable
from pathlib import Path

import pytest

from dvb_usb_com.framing import decode_frame, encode_frame
from dvb_usb_com.messages import (
    MESSAGES,
    ControlParam,
    Cup,
    Door,
    Heartbeat,
    Message,
    MessageError,
    Messages,
    MotionState,
    MotionStatus,
    Move,
    MoveFlags,
    MoveKind,
    Nack,
    Pickup,
    Print,
    ResetPose,
    SetControlParams,
    StartTrace,
    StatusFlags,
    StepperStep,
    Stop,
    StopMode,
    Tower,
    TraceEnd,
    TraceKind,
    TraceLoop,
    TraceSample,
    Wall,
    decode_message,
)

type CppTool = Callable[[str, list[str]], list[str]]

MESSAGES_H = Path(__file__).parents[1] / "cpp" / "include" / "messages.h"


def header_ids() -> dict[str, int]:
    """IDs of messages.h, by name."""
    text = MESSAGES_H.read_text(encoding="utf-8")
    return {name: int(value) for name, value in re.findall(r"^#define (\w+) (\d+)$", text, re.M)}


def test_same_ids_and_sizes_as_messages_h(cpp_tool: CppTool) -> None:
    cpp = {}
    for line in cpp_tool("sizes", []):
        name, message_id, size = line.split()
        assert int(message_id) not in cpp, f"two structures with id {message_id}"
        cpp[int(message_id)] = (name, int(size))

    python = {message_id: cls.size() for message_id, cls in MESSAGES.items()}
    assert set(cpp) == set(python)
    for message_id, (name, size) in cpp.items():
        assert size == python[message_id], f"{name}: {size} bytes in C++, {python[message_id]} here"


def test_every_id_of_messages_h_is_known() -> None:
    known = set(MESSAGES) | {Print.ID}
    assert set(header_ids().values()) == known


def test_message_ids_are_those_of_the_header() -> None:
    assert {message.name: message.value for message in Messages} == header_ids()


def test_sizes_of_the_adr() -> None:
    # sizes written in docs/adr/0003-motion-protocol.md
    assert Move.size() == 29
    assert ResetPose.size() == 13
    assert SetControlParams.size() == 6
    assert StartTrace.size() == 19
    assert MotionStatus.size() == 39
    assert TraceSample.size() == 25
    assert TraceEnd.size() == 16


@pytest.mark.parametrize(
    "message",
    [
        Move(
            7, MoveKind.GOTO, MoveFlags.REVERSE | MoveFlags.HAS_HEADING, 1.5, 0.25, -0.5, 0, 0.5, 1
        ),
        SetControlParams(ControlParam.PUSH_VOLTAGE, 4.0),
        ResetPose(0.125, 1.75, 3.0),
        Stop(StopMode.URGENT),
        StartTrace(TraceKind.CLOSED_LOOP_STEP, TraceLoop.HEADING, 0, 0.5, 1, 2),
        Heartbeat(65535),
        Nack(),
        MotionStatus(
            3,
            MotionState.BLOCKED,
            StatusFlags.CONFIGURED,
            1,
            2,
            0.5,
            0.25,
            -1,
            15.5,
            1000,
            2**32 - 1,
            42,
        ),
        TraceSample(5, 0.5, 0.25, 3.0, -3.0, 14.5),
        TraceEnd(400, MotionState.ARRIVED, 0.0078125, 40, 400),
        StepperStep(-200, True, 800, 1, 2, 3),
        Door(),
        Pickup(),
        Cup(),
        Wall(),
        Tower(),
    ],
)
def test_pack_unpack_round_trip(message: Message) -> None:
    data = message.pack()
    assert len(data) == type(message).size()
    assert data[0] == message.ID
    # through a frame, as on the serial link; the values are exact in float32
    assert decode_message(decode_frame(encode_frame(data)[:-1])) == message


def test_enums_are_restored() -> None:
    status = decode_message(
        MotionStatus(1, MotionState.ARRIVED, StatusFlags(5), 0, 0, 0, 0, 0, 0, 0, 0, 0).pack()
    )
    assert isinstance(status, MotionStatus)
    assert status.state is MotionState.ARRIVED
    assert status.flags == StatusFlags.CONFIGURED | StatusFlags.HEARTBEAT_LOST


def test_print_message() -> None:
    assert decode_message(bytes([254]) + b"hello") == Print("hello")
    assert Print("hi").pack() == b"\xfehi"


def test_bad_messages() -> None:
    with pytest.raises(MessageError, match="unknown message id"):
        decode_message(bytes([42]))
    with pytest.raises(MessageError, match="expected 13 bytes"):
        decode_message(ResetPose(0, 0, 0).pack()[:-1])
    with pytest.raises(MessageError, match="MotionStatus"):
        bad_state = bytearray(MotionStatus(1, MotionState.MOVING, StatusFlags(0), *[0] * 9).pack())
        bad_state[3] = 9
        decode_message(bytes(bad_state))
    with pytest.raises(MessageError, match="empty"):
        decode_message(b"")
