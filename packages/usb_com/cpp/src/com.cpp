#include <Arduino.h>
#include <com.h>
#include <string.h>

Com::Com(usb_serial_class* stream, uint32_t baudrate) {
    this->stream = stream;
    stream->begin(baudrate);
}

Com::Com(HardwareSerial* stream, uint32_t baudrate) {
    this->stream = stream;
    stream->begin(baudrate);
}

byte Com::handle() {
    while (this->stream->available()) {
        uint8_t data = this->stream->read();

        if (data != 0x00) {
            // a frame longer than the largest one cannot be valid
            if (this->rx_size >= sizeof(this->rx)) {
                this->rx_overflow = true;
            } else {
                this->rx[this->rx_size++] = data;
            }
            continue;
        }

        // 0x00: end of frame
        uint16_t size = this->rx_size;
        bool overflow = this->rx_overflow;
        this->rx_size = 0;
        this->rx_overflow = false;
        if (size == 0) {
            continue;
        }

        size_t msg_size =
            overflow ? 0 : usb_com::decode_frame(this->rx, size, this->msg);
        if (msg_size == 0) {
            byte nack = NACK;
            this->send_msg(&nack, 1);
            continue;
        }
        return (byte)msg_size;
    }
    return 0;
}

void Com::handle_callback(void (*functions[256])(byte* msg, byte size)) {
    byte size = this->handle();
    if (size == 0) {
        return;
    }

    byte msg_id = this->msg[0];
    if (functions[msg_id] != nullptr) {
        functions[msg_id](this->msg, size);
    } else if (msg_id == NACK) {
        // the Pi did not receive our last message correctly
        if (this->last_msg_size > 0) {
            this->send_msg(this->last_msg, this->last_msg_size, true);
        }
    } else {
        msg_unknown_msg_type error_message;
        error_message.type_id = msg_id;
        this->send_msg((byte*)&error_message, sizeof(msg_unknown_msg_type));
    }
}

byte* Com::read_buffer() {
    return this->msg;
}

void Com::write_frame(const uint8_t* data, uint8_t size) {
    uint8_t frame[usb_com::MAX_FRAME_SIZE];
    size_t frame_size = usb_com::encode_frame(data, size, frame);
    if (frame_size > 0) {
        this->stream->write(frame, frame_size);
    }
}

void Com::send_msg(byte* msg, byte size, bool is_nack) {
    if (size == 0) {
        return;
    }
    // a NACK is never retransmitted: it would answer the retransmission
    if (!is_nack && msg[0] != NACK) {
        memcpy(this->last_msg, msg, size);
        this->last_msg_size = size;
    }
    this->write_frame(msg, size);
}

void Com::print(const char* text) {
    if (!this->print_enabled) {
        return;
    }
    uint8_t msg[usb_com::MAX_MSG_SIZE];
    size_t length = strnlen(text, usb_com::MAX_MSG_SIZE - 1);
    msg[0] = PRINT;
    memcpy(msg + 1, text, length);
    this->send_msg(msg, length + 1);
}
