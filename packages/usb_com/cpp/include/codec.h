/**
 * Framing of the Pi <-> Teensy messages, without any Arduino dependency so
 * that it also compiles on a PC (tests, virtual Teensy).
 *
 * Frame: [msg_id u8][payload N][len u8][crc16 u16 LE] -> COBS -> 0x00
 * - len is the message size, id included (1 to 255);
 * - CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) over the message and len.
 * See docs/adr/0003-motion-protocol.md.
 */

#ifndef USB_COM_CODEC_H
#define USB_COM_CODEC_H

#include <stddef.h>
#include <stdint.h>

namespace usb_com {

// largest message, id included
constexpr size_t MAX_MSG_SIZE = 255;
// message + len + crc, before COBS
constexpr size_t MAX_RAW_SIZE = MAX_MSG_SIZE + 3;
// COBS adds one byte per 254 bytes (rounded up), plus the 0x00 delimiter
constexpr size_t MAX_FRAME_SIZE = MAX_RAW_SIZE + (MAX_RAW_SIZE + 253) / 254 + 1;

/**
 * @brief CRC-16/CCITT-FALSE, the same as binascii.crc_hqx(data, 0xFFFF)
 */
uint16_t crc16(const uint8_t* data, size_t size);

/**
 * @brief COBS encoding: the output contains no 0x00
 *
 * @param out Must hold at least size + size / 254 + 1 bytes
 * @return Number of bytes written
 */
size_t cobs_encode(const uint8_t* in, size_t size, uint8_t* out);

/**
 * @brief COBS decoding
 *
 * @return Number of bytes written, 0 if the input is not valid COBS or does
 * not fit in out_capacity
 */
size_t cobs_decode(const uint8_t* in,
                   size_t size,
                   uint8_t* out,
                   size_t out_capacity);

/**
 * @brief Builds the frame of a message, 0x00 delimiter included
 *
 * @param out Must hold MAX_FRAME_SIZE bytes
 * @return Frame size, 0 if size is 0 or above MAX_MSG_SIZE
 */
size_t encode_frame(const uint8_t* msg, size_t size, uint8_t* out);

/**
 * @brief Extracts the message of a frame
 *
 * @param frame Frame without its 0x00 delimiter
 * @param msg Must hold MAX_MSG_SIZE bytes
 * @return Message size, 0 if the frame is damaged (COBS, len or CRC)
 */
size_t decode_frame(const uint8_t* frame, size_t size, uint8_t* msg);

}  // namespace usb_com

#endif  // USB_COM_CODEC_H
