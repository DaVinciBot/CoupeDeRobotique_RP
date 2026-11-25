#ifndef USB_COM_MESSAGES_H
#define USB_COM_MESSAGES_H

#if defined(ARDUINO)
#include <Arduino.h>
#else
// compiled on a PC by the protocol tests
#include <stdint.h>
typedef uint8_t byte;
#endif

// No padding between the fields: the layout is the same on the Teensy, on a
// PC and in messages.py. push/pop keeps this setting inside this file only.
#pragma pack(push, 1)

// Rolling base messages: docs/adr/0003-motion-protocol.md. SI units, float
// fields (32 bits), little endian. messages.py must stay identical: the CI
// compares the IDs and sizes.

// ====== Message IDs ======
// Pi -> Teensy: 0-127

// Rolling base
#define MOVE 0
#define SET_CONTROL_PARAMS 1
#define RESET_POSE 2
#define STOP 9
#define START_TRACE 10

// Actuators
#define SET_SERVO_ANGLE_I2C 3
#define STEPPER_STEP 4
#define SET_SERVO_ANGLE_DETACH 5
#define ATTACH_SWITCH 6
#define SET_SERVO_ANGLE 7
#define SET_STEPPER_DRIVER_ACTIVATION_STATE 8
// Provisional: content to be defined with the actuator board contract (TODO 12.2)
#define DOOR 11
#define PICKUP 12
#define CUP 13
#define WALL 14
#define TOWER 15

// Common (rolling base + actuators)
#define HEARTBEAT 125
#define RESET_TEENSY 126

// Both ways: 127
#define NACK 127

// Teensy -> Pi: 128-255
// Rolling base
#define MOTION_STATUS 128
#define TRACE_SAMPLE 130
#define TRACE_END 131

// Actuators
#define SWITCH_STATE_RETURN 129

// Common (rolling base + actuators)
#define PRINT 254
#define UNKNOWN_MSG_TYPE 255

// ====== Pi -> Teensy ======

// Rolling base
// kind: 0 ROTATE_BY (theta), 1 ROTATE_TO (theta), 2 STRAIGHT (distance),
// 3 GOTO (x, y, theta if HAS_HEADING), 4 PUSH_UNTIL_BLOCKED (distance = max
// distance, signed). flags: bit 0 REVERSE, bit 1 HAS_HEADING.
struct msg_move
{
    byte command = MOVE;
    uint16_t move_id;  // chosen by the brain, 0 is reserved
    byte kind;
    byte flags;
    float x;          // m
    float y;          // m
    float theta;      // rad
    float distance;   // m, negative = backwards
    float max_speed;  // m/s, 0 = configured limit
    float max_accel;  // m/s², 0 = configured limit
};

// One setting per message; the Teensy stays inert until it has received
// every setting once
struct msg_set_control_params
{
    byte command = SET_CONTROL_PARAMS;
    byte param;   // motion::Param
    float value;  // SI unit of the setting
};

// Ignored while moving: the brain checks the pose in the next status
struct msg_reset_pose
{
    byte command = RESET_POSE;
    float x;      // m
    float y;      // m
    float theta;  // rad
};

struct msg_stop
{
    byte command = STOP;
    byte mode;  // 0 SMOOTH (generator braking), 1 URGENT (command to zero)
};

// kind: 0 OPEN_LOOP_STEP (V), 1 CLOSED_LOOP_STEP (unit of the loop).
// loop: 0 LEFT_SPEED, 1 RIGHT_SPEED, 2 DISTANCE, 3 HEADING
struct msg_start_trace
{
    byte command = START_TRACE;
    byte kind;
    byte loop;
    float initial;    // before step_time
    float final;      // from step_time
    float step_time;  // s
    float duration;   // s, at most 10 s
};

// Actuators
struct msg_set_servo_angle
{
    byte command = SET_SERVO_ANGLE;
    byte pin;           // pin to which the servo is connected
    uint16_t angle;     // angle to which the servo should be moved in degrees
    uint16_t max_angle; // max angle reachable by the servo ex : 180, 270
};

struct msg_set_servo_angle_I2C
{
    byte command = SET_SERVO_ANGLE_I2C;
    byte pin;           // pin to which the servo is connected
    uint16_t angle;     // angle to which the servo should be moved in degrees
    uint16_t max_angle; // max angle reachable by the servo ex : 180, 270
};

struct msg_set_servo_angle_detach
{
    byte command = SET_SERVO_ANGLE_DETACH;
    byte pin;           // pin to which the servo is connected
    uint16_t angle;     // angle to which the servo should be moved in degrees
    uint16_t max_angle; // max angle reachable by the servo ex : 180, 270
    int detach_delay;   // delay in milliseconds before detaching the servo
};

struct msg_stepper_step
{
    byte command = STEPPER_STEP;
    int steps;              // total number of steps this motor can take
    bool dir;               // direction of the motor
    int speed;              // speed
    byte pin_dir;           // pin to which the direction pin is connected
    byte pin_step;          // pin to which the step pin is connected
    byte enable_pin_driver; // pin to which the driver pin is connected
};

struct msg_set_stepper_driver_activation_state
{
    byte command = SET_STEPPER_DRIVER_ACTIVATION_STATE;
    byte pin;                 // stepper driver's enable pin
    bool enable_driver_state; // active low so true means the driver is disabled
};

struct msg_attach_switch
{
    byte command = ATTACH_SWITCH;
    byte pin; // pin to which the servo is connected
};

// Provisional: only the id for now, the fields come with the actuator board
// contract (TODO 12.2)
struct msg_door
{
    byte command = DOOR;
};

struct msg_pickup
{
    byte command = PICKUP;
};

struct msg_cup
{
    byte command = CUP;
};

struct msg_wall
{
    byte command = WALL;
};

struct msg_tower
{
    byte command = TOWER;
};

// Common (rolling base + actuators)
// Sent at 20 Hz: without it for 200 ms, the Teensy brakes and stops
struct msg_heartbeat
{
    byte command = HEARTBEAT;
    uint16_t counter;
};

struct msg_reset_teensy
{
    byte command = RESET_TEENSY;
};

struct msg_nack
{
    byte command = NACK;
};

// ====== Teensy -> Pi ======

// Rolling base
// Every 50 ms. state: 0 MOVING, 1 ARRIVED, 2 BLOCKED, 3 STOPPED. flags: bit 0
// CONFIGURED, 1 EMERGENCY_STOP, 2 HEARTBEAT_LOST, 3 VBAT_MISSING,
// 4 ESTOP_SENSOR_MISSING, 5 TRACE_RUNNING
struct msg_motion_status
{
    byte command = MOTION_STATUS;
    uint16_t move_id;  // last MOVE accepted
    byte state;
    byte flags;
    float x;           // m
    float y;           // m
    float theta;       // rad
    float v;           // m/s
    float omega;       // rad/s
    float vbat;        // V
    uint32_t time_ms;  // Teensy time since start-up
    uint32_t boot_id;  // random, changes at each start-up
    uint16_t heartbeat;  // last HEARTBEAT counter received
};

// Every period during a trace
struct msg_trace_sample
{
    byte command = TRACE_SAMPLE;
    uint32_t time_ms;  // since the start of the trace
    float setpoint;
    float measurement;
    float u_left;   // V
    float u_right;  // V
    float vbat;     // V
};

struct msg_trace_end
{
    byte command = TRACE_END;
    uint16_t sample_count;
    byte state;  // as in msg_motion_status
    float ts;    // s
    float kp;    // gains really used by the loop of the trace
    float ki;
};

// Actuators
struct msg_switch_state_return
{
    byte command = SWITCH_STATE_RETURN;
    byte pin;   // pin of the switch
    bool state; // switch state
};

// Common (rolling base + actuators)
// PRINT has no structure: the id is followed by ASCII text
struct msg_unknown_msg_type
{
    byte command = UNKNOWN_MSG_TYPE;
    byte type_id; // ID of the unknown message
};

#pragma pack(pop)

#endif  // USB_COM_MESSAGES_H
