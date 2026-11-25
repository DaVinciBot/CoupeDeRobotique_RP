#include <Arduino.h>
#include <com.h>
#include <cstring>  // To use memcpy()

/**
 * @brief Constructor for USB serial communication.
 *
 * Initializes the communication stream for USB serial and sets up the internal buffer.
 *
 * @param stream Pointer to the USB serial class.
 * @param baudrate Baud rate for serial communication.
 */
Com::Com(usb_serial_class *stream, uint32_t baudrate)
{
    this->stream = stream;
    stream->begin(baudrate);

    // Initialize the buffer
    for (uint16_t k = 0; k < usb_com::MAX_FRAME_SIZE; k++)
        this->buffer[k] = 0;
}

/**
 * @brief Constructor for hardware serial communication.
 *
 * Initializes the communication stream for hardware serial and sets up the internal buffer.
 *
 * @param stream Pointer to the hardware serial class.
 * @param baudrate Baud rate for serial communication.
 */
Com::Com(HardwareSerial *stream, uint32_t baudrate)
{
    this->stream = stream;
    stream->begin(baudrate);

    // Initialize the buffer
    for (uint16_t k = 0; k < usb_com::MAX_FRAME_SIZE; k++)
        this->buffer[k] = 0;
}

/**
 * @brief Handles incoming data from the communication stream.
 *
 * Processes incoming data byte by byte up to the end of a frame, checks it (COBS, size and CRC-16),
 * and extracts the message size if a valid message is detected.
 *
 * @return The size of the valid message, or 0 if no valid message is found.
 */
byte Com::handle()
{
    while (this->stream->available())
    {
        byte data = this->stream->read();

        // 0x00 only appears at the end of a frame (COBS)
        if (data != 0x00)
        {
            // A frame that fills the buffer is too long: dropped at its 0x00
            if (this->pointer < usb_com::MAX_FRAME_SIZE)
                this->buffer[this->pointer++] = data;
            continue;
        }

        uint16_t frame_size = this->pointer;
        this->pointer = 0;
        if (frame_size == 0)
            continue;

        // Decoded in place: the message is at the start of the buffer
        size_t msg_size = 0;
        if (frame_size < usb_com::MAX_FRAME_SIZE)
            msg_size = usb_com::decode_frame(this->buffer, frame_size, this->buffer);

        if (msg_size == 0)
        {
            byte invalid_crc_msg = NACK;
            send_msg(&invalid_crc_msg, 1);
            continue;
        }

        return (byte)msg_size;
    }
    return 0;
}

/**
 * @brief Handles callbacks for received messages.
 *
 * Processes received messages, retrieves the message ID, and calls the corresponding callback function
 * from the provided function array. Handles unknown messages and retransmits the last message in case of NACK.
 *
 * @param functions Array of callback functions indexed by message ID.
 */
void Com::handle_callback(void (*functions[256])(byte *msg, byte size))
{
    // Retrieve the size of the received message
    byte size = this->handle();
    if (size > 0)
    {
        // Directly access the buffer pointer
        const byte *msg = this->read_buffer();
        if (msg == nullptr)
        {
            // Exit if the buffer is null (protection)
            return;
        }

        // Retrieve the message ID
        byte msg_id = msg[0];

        // Check if the function corresponding to the ID exists
        if (functions[msg_id] != nullptr)
        {
            functions[msg_id](const_cast<byte *>(msg), size); // Call the function
        }
        else if (msg_id == NACK)
        {
            // Resend the last message in case of NACK
            if (this->last_msg->size > 0)
            {
                this->send_msg((byte *)&this->last_msg->msg, this->last_msg->size, true);
            }
        }
        else
        {
            // Handle unknown message types
            msg_unknown_msg_type error_message;
            error_message.type_id = msg_id;

            // Send a response indicating an unknown message type
            this->send_msg((byte *)&error_message, sizeof(msg_unknown_msg_type));
        }
    }
}

/**
 * @brief Provides access to the internal buffer.
 *
 * @return Pointer to the internal buffer.
 */
byte *Com::read_buffer()
{
    return this->buffer;
}

/**
 * @brief Sends a message over the communication stream.
 *
 * Stores the message as the last message (if not a NACK), and sends its frame over the stream.
 *
 * @param msg Pointer to the message data to send.
 * @param size The size of the message data.
 * @param is_nack Indicates if the message is a retransmission due to a NACK.
 */
void Com::send_msg(byte *msg, byte size, bool is_nack)
{
    // A NACK is not kept: the Pi would ask for it again instead of the lost message
    if (!is_nack && size > 0 && msg[0] != NACK)
    {
        memcpy(this->last_msg->msg, msg, size);
        this->last_msg->size = size;
    }

    // Send the frame
    byte frame[usb_com::MAX_FRAME_SIZE];
    size_t frame_size = usb_com::encode_frame(msg, size, frame);
    this->stream->write(frame, frame_size);
    this->stream->flush();
}

/**
 * @brief Sends a debug text message.
 *
 * This function sends a text message for debugging purposes. The message must be in ASCII format
 * and cannot exceed 253 characters.
 *
 * @param text Pointer to the null-terminated ASCII text string to send.
 */
void Com::print(char *text)
{
    if (!this->print_enabled)
        return;

    // Use send_msg to send the text input
    byte msg[usb_com::MAX_MSG_SIZE];
    size_t length = strnlen(text, 253);
    msg[0] = PRINT;
    memcpy(msg + 1, text, length);
    this->send_msg(msg, length + 1);
}
