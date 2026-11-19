/*
 * Configuration of the motor Teensy: pins and hardware constants, in SI
 * units. The control settings (gains, speed limits, tolerances, blocking
 * thresholds) are not here: the brain sends them at start-up from
 * config/robot.json, and the Teensy stays inert until it has them all.
 */

#ifndef CONFIG_H
#define CONFIG_H

// Motor Left
#define L_ENCA 12
#define L_ENCB 11
#define L_PWM 5
#define L_DIR 4  // to be checked with the wiring

// Motor Right
#define R_ENCA 14
#define R_ENCB 13
#define R_PWM 2
#define R_DIR 0  // to be checked with the wiring

// Encoder wheels (AMT102-V), to be measured on the robot (Q2 of the control
// design document)
#define ENCODER_RESOLUTION 4096  // counts per turn after x4 decoding: DIP switch to check
#define ENCODER_WHEEL_DIAMETER 0.059  // m
#define TRACK_WIDTH 0.295             // distance between the encoder wheels, m

// PWM + DIR, 30 to 40 kHz (R4)
#define PWM_FREQUENCY 40000
#define PWM_RESOLUTION 12
#define PWM_MAX 4095  // (2 ** PWM_RESOLUTION) - 1

// Loop period until the brain sends LOOP_PERIOD
#define LOOP_PERIOD_DEFAULT 0.005  // s

// Com baudrate (ignored by the USB serial of the Teensy)
#define BAUDRATE 115200

// Motor voltage limit (Faulhaber 3242G012CR, 12 V)
#define U_MAX 12.0  // V

// Battery voltage (R7): pin of the filtered divider and its ratio, to be
// given by the elec team. Until then VBAT_DEFAULT is used and the status
// says VBAT_MISSING.
// #define VBAT_PIN A0
// #define VBAT_DIVIDER_RATIO 6.0  // vbat = voltage on the pin * ratio
#define VBAT_DEFAULT 14.8  // V, 4S LiPo

// Emergency stop sense (R2): pin reading the power after the emergency stop
// button, to be given by the elec team. Until then the status says
// ESTOP_SENSOR_MISSING.
// #define ESTOP_PIN 22
// #define ESTOP_ACTIVE_LEVEL LOW  // level on the pin when the power is cut

// Safety: never longer without an ADR (architecture, section 11)
#define HEARTBEAT_TIMEOUT 0.2  // s

// MOTION_STATUS period (architecture 6.1: 10 Hz at least)
#define STATUS_PERIOD 0.05  // s

#define MAX_TRACE_DURATION 10.0  // s
#define CONTINUE_ANGLE 0.1745    // 10 deg: heading gap under which a GOTO goes on, rad

#endif  // CONFIG_H
