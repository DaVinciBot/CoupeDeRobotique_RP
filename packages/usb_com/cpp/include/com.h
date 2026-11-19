#ifndef USB_COM_COM_H
#define USB_COM_COM_H

#include <Arduino.h>
#include <codec.h>
#include <messages.h>

/**
 * @brief Serial link with the Raspberry Pi
 *
 * Frames are cut by COBS and checked by a CRC-16 (codec.h). A damaged frame
 * is dropped and answered with a NACK; a NACK received triggers the
 * retransmission of the last message sent.
 */
class Com {
   private:
    Stream* stream;  ///< USB or hardware serial

    uint8_t rx[usb_com::MAX_FRAME_SIZE];  ///< frame being received
    uint16_t rx_size = 0;
    bool rx_overflow = false;  ///< frame too long: dropped up to the next 0x00

    uint8_t msg[usb_com::MAX_MSG_SIZE];  ///< last message received

    uint8_t last_msg[usb_com::MAX_MSG_SIZE];  ///< last message sent
    uint8_t last_msg_size = 0;

    void write_frame(const uint8_t* data, uint8_t size);

   public:
    /**
     * @brief Constructor for USB serial communication
     *
     * @param stream Pointer to the USB serial class
     * @param baudrate Baud rate (ignored by the Teensy USB serial)
     */
    Com(usb_serial_class* stream, uint32_t baudrate);

    /**
     * @brief Constructor for hardware serial communication
     *
     * @param stream Pointer to the hardware serial class
     * @param baudrate Baud rate for serial communication
     */
    Com(HardwareSerial* stream, uint32_t baudrate);

    /**
     * @brief Reads the bytes available on the stream
     *
     * Stops at the first complete and valid message.
     *
     * @return Size of the message (available with read_buffer()), 0 if no
     * complete message was received
     */
    byte handle();

    /**
     * @brief Reads the stream and calls the callback of each message received
     *
     * The callback receives the message (id included) and its size, which it
     * must check before reading the fields. A message without callback is
     * answered with UNKNOWN_MSG_TYPE.
     *
     * @param functions Array of callback functions indexed by message ID
     */
    void handle_callback(void (*functions[256])(byte* msg, byte size));

    /**
     * @brief Last message received by handle()
     */
    byte* read_buffer();

    /**
     * @brief Sends a message (id included)
     *
     * @param msg Message to send
     * @param size Message size, 1 to 255
     * @param is_nack True for a retransmission: the message is not saved again
     */
    void send_msg(byte* msg, byte size, bool is_nack = false);

    /**
     * @brief Sends a debug text in a PRINT message, if print_enabled is true
     *
     * @param text Null-terminated ASCII text, cut at 254 characters
     */
    void print(const char* text);

    bool print_enabled = false;  ///< PRINT is for debug only (TODO 13.4)
};

#endif  // USB_COM_COM_H
