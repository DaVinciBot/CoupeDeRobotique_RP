"""Com of the Pi on a fake serial port."""

import logging
import threading
import time
from types import SimpleNamespace

import pytest

from dvb_usb_com import Com, ComError, DummySerial, FrameDecoder, Messages, encode_frame
from dvb_usb_com.com import com as com_module

# FakeSerial ends the receiver thread with SystemExit
pytestmark = pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")

LOGGER = logging.getLogger("test_com")
STATUS = Messages.MOTION_STATUS.to_bytes() + b"abc"


class FakeSerial:
    """Gives the prepared frames, then ends the receiver thread."""

    def __init__(self, frames: list[bytes]) -> None:
        self.frames = list(frames)
        self.sent = bytearray()
        self.out_waiting = 0
        self.start = threading.Event()  # the test registers its callbacks first

    def read_until(self, delimiter: bytes) -> bytes:
        # SystemExit is not caught by the receiver: the thread ends, even if the test failed
        if not self.start.wait(5.0) or not self.frames:
            raise SystemExit
        return self.frames.pop(0)

    def reset_output_buffer(self) -> None:
        pass  # the sent bytes are already gone: out_waiting is always 0

    def write(self, data: bytes) -> None:
        # byte by byte, so that two writers without a lock would mix their frames
        for byte in data:
            self.sent.append(byte)
            time.sleep(0)


def make_com(
    monkeypatch: pytest.MonkeyPatch, frames: list[bytes], *, enable_crc: bool = True
) -> tuple[Com, FakeSerial]:
    device = FakeSerial(frames)
    port = SimpleNamespace(device="COM1", vid=1, pid=2, serial_number="42")
    monkeypatch.setattr(com_module, "comports", lambda: [port])
    monkeypatch.setattr(com_module, "Serial", lambda *_args, **_kwargs: device)
    return Com(LOGGER, 42, 1, 2, 115200, enable_crc=enable_crc), device


def run_receiver(com: Com, device: FakeSerial) -> None:
    device.start.set()
    assert com._receiver_thread is not None
    com._receiver_thread.join(5.0)
    assert not com._receiver_thread.is_alive()


def damaged(message: bytes) -> bytes:
    frame = bytearray(encode_frame(message))
    frame[-2] ^= 0x01 if frame[-2] != 0x01 else 0x02  # never a 0x00
    return bytes(frame)


def sent_messages(device: FakeSerial) -> list[bytes]:
    decoder = FrameDecoder()
    messages = decoder.feed(bytes(device.sent))
    assert decoder.errors == 0
    return messages


def test_callback_receives_the_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    com, device = make_com(monkeypatch, [encode_frame(STATUS)])
    received: list[bytes] = []
    com.add_callback(received.append, Messages.MOTION_STATUS.value)
    run_receiver(com, device)
    assert received == [b"abc"]


def test_damaged_frame_is_answered_with_a_nack(monkeypatch: pytest.MonkeyPatch) -> None:
    com, device = make_com(monkeypatch, [damaged(STATUS), encode_frame(STATUS)])
    received: list[bytes] = []
    com.add_callback(received.append, Messages.MOTION_STATUS.value)
    run_receiver(com, device)
    assert sent_messages(device) == [Messages.NACK.to_bytes()]
    assert received == [b"abc"]


def test_crc_check_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    com, device = make_com(monkeypatch, [damaged(STATUS)], enable_crc=False)
    received: list[bytes] = []
    com.add_callback(received.append, Messages.MOTION_STATUS.value)
    run_receiver(com, device)
    assert received == [b"abc"]


def test_nack_resends_the_last_message_once(monkeypatch: pytest.MonkeyPatch) -> None:
    nack = encode_frame(Messages.NACK.to_bytes())
    com, device = make_com(monkeypatch, [nack, nack])
    com.send_bytes(b"\x01hello")
    run_receiver(com, device)
    assert sent_messages(device) == [b"\x01hello", b"\x01hello"]


def test_sent_nack_does_not_replace_the_last_message(monkeypatch: pytest.MonkeyPatch) -> None:
    nack = encode_frame(Messages.NACK.to_bytes())
    com, device = make_com(monkeypatch, [damaged(STATUS), nack])
    com.send_bytes(b"\x01hello")
    run_receiver(com, device)
    assert sent_messages(device) == [b"\x01hello", Messages.NACK.to_bytes(), b"\x01hello"]


def test_two_writers_do_not_mix_their_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    com, device = make_com(monkeypatch, [])
    run_receiver(com, device)

    def send(message_id: int) -> None:
        for _ in range(50):
            com.send_bytes(bytes([message_id]) * 20)

    threads = [threading.Thread(target=send, args=(i,)) for i in (1, 2, 3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10.0)
    messages = sent_messages(device)
    assert len(messages) == 150
    assert {m: messages.count(m) for m in set(messages)} == {bytes([i]) * 20: 50 for i in (1, 2, 3)}


@pytest.mark.parametrize(
    "port",
    [
        SimpleNamespace(device="COM1", vid=1, pid=2, serial_number="43"),
        SimpleNamespace(device="COM1", vid=1, pid=2, serial_number=None),
        SimpleNamespace(device="COM1", vid=9, pid=2, serial_number="42"),
    ],
)
def test_other_devices_are_not_opened(
    monkeypatch: pytest.MonkeyPatch, port: SimpleNamespace
) -> None:
    monkeypatch.setattr(com_module, "comports", lambda: [port])
    with pytest.raises(ComError):
        Com(LOGGER, 42, 1, 2, 115200)


def test_dummy_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(com_module, "comports", lambda: [])
    com = Com(LOGGER, 42, 1, 2, 115200, enable_dummy=True)
    com.send_bytes(b"\x01hello")
    com.send_bytes(b"\x02bye")
    assert isinstance(com._device, DummySerial)
    assert com._device.output_buffer == encode_frame(b"\x02bye")
