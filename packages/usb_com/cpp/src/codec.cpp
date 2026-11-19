#include <codec.h>

namespace usb_com {

uint16_t crc16(const uint8_t* data, size_t size) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < size; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (int bit = 0; bit < 8; bit++) {
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021)
                                 : (uint16_t)(crc << 1);
        }
    }
    return crc;
}

size_t cobs_encode(const uint8_t* in, size_t size, uint8_t* out) {
    // each block starts with the distance to the next 0x00 (or to the end)
    size_t code_index = 0;
    size_t write_index = 1;
    uint8_t code = 1;

    for (size_t i = 0; i < size; i++) {
        if (in[i] == 0) {
            out[code_index] = code;
            code_index = write_index++;
            code = 1;
            continue;
        }
        out[write_index++] = in[i];
        code++;
        // a full block of 254 non-zero bytes has no implicit 0x00
        if (code == 0xFF) {
            out[code_index] = code;
            code_index = write_index++;
            code = 1;
        }
    }
    out[code_index] = code;
    return write_index;
}

size_t cobs_decode(const uint8_t* in,
                   size_t size,
                   uint8_t* out,
                   size_t out_capacity) {
    size_t read_index = 0;
    size_t write_index = 0;

    while (read_index < size) {
        uint8_t code = in[read_index++];
        if (code == 0 || read_index + code - 1 > size) {
            return 0;
        }
        for (uint8_t i = 1; i < code; i++) {
            if (write_index >= out_capacity) {
                return 0;
            }
            out[write_index++] = in[read_index++];
        }
        // the block stands for a 0x00, except a full block or the last one
        if (code != 0xFF && read_index < size) {
            if (write_index >= out_capacity) {
                return 0;
            }
            out[write_index++] = 0;
        }
    }
    return write_index;
}

size_t encode_frame(const uint8_t* msg, size_t size, uint8_t* out) {
    if (size == 0 || size > MAX_MSG_SIZE) {
        return 0;
    }

    uint8_t raw[MAX_RAW_SIZE];
    for (size_t i = 0; i < size; i++) {
        raw[i] = msg[i];
    }
    raw[size] = (uint8_t)size;
    uint16_t crc = crc16(raw, size + 1);
    raw[size + 1] = crc & 0xFF;
    raw[size + 2] = crc >> 8;

    size_t length = cobs_encode(raw, size + 3, out);
    out[length] = 0x00;
    return length + 1;
}

size_t decode_frame(const uint8_t* frame, size_t size, uint8_t* msg) {
    uint8_t raw[MAX_RAW_SIZE];
    size_t raw_size = cobs_decode(frame, size, raw, MAX_RAW_SIZE);
    // at least an id, len and the crc
    if (raw_size < 4) {
        return 0;
    }

    size_t msg_size = raw_size - 3;
    if (raw[msg_size] != msg_size) {
        return 0;
    }
    uint16_t crc = raw[msg_size + 1] | (uint16_t)raw[msg_size + 2] << 8;
    if (crc != crc16(raw, msg_size + 1)) {
        return 0;
    }

    for (size_t i = 0; i < msg_size; i++) {
        msg[i] = raw[i];
    }
    return msg_size;
}

}  // namespace usb_com
