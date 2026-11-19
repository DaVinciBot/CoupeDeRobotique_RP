/**
 * Motor Teensy: control of the rolling base.
 *
 * - The timer calls control_loop() at each period: it reads the encoders,
 *   the battery and the emergency stop, runs the controller and applies the
 *   voltages. It also prepares the messages for the Pi.
 * - loop() reads the messages of the Pi and sends the prepared ones.
 *
 * Messages: docs/adr/0003-motion-protocol.md. Every call to the controller
 * made from loop() is done with the timer interrupt blocked.
 */

#include <Arduino.h>
#include <Entropy.h>
#include <TimerOne.h>
#include <com.h>
#include <config.h>
#include <motion_controller.h>
#include <motors_driver.h>
#include <string.h>
#include <util/atomic.h>

using namespace motion;

Motor left_motor(L_DIR, L_PWM, L_ENCA, L_ENCB, PWM_MAX, U_MAX);
Motor right_motor(R_DIR, R_PWM, R_ENCA, R_ENCB, PWM_MAX, U_MAX);

const Config CONTROL_CONFIG = {
    kPi * ENCODER_WHEEL_DIAMETER / ENCODER_RESOLUTION,  // tick_distance
    TRACK_WIDTH,
    U_MAX,
    HEARTBEAT_TIMEOUT,
    MAX_TRACE_DURATION,
    CONTINUE_ANGLE,
};
MotionController controller(CONTROL_CONFIG, LOOP_PERIOD_DEFAULT);

Com* com;
uint32_t boot_id = 0;
uint16_t last_heartbeat = 0;

// sensors not wired yet: reported in every status
const uint8_t HARDWARE_FLAGS =
#ifndef VBAT_PIN
    status_flags::VBAT_MISSING |
#endif
#ifndef ESTOP_PIN
    status_flags::ESTOP_SENSOR_MISSING |
#endif
    0;

// Messages prepared by the timer, sent by loop()
msg_motion_status status_msg;
volatile bool status_ready = false;
msg_trace_sample sample_msg;
volatile bool sample_ready = false;
msg_trace_end trace_end_msg;
volatile bool trace_end_ready = false;
uint32_t periods_since_status = 0;

double read_vbat() {
#ifdef VBAT_PIN
    return analogRead(VBAT_PIN) * 3.3 / 1023.0 * VBAT_DIVIDER_RATIO;
#else
    return VBAT_DEFAULT;
#endif
}

bool read_emergency_stop() {
#ifdef ESTOP_PIN
    return digitalRead(ESTOP_PIN) == ESTOP_ACTIVE_LEVEL;
#else
    return false;
#endif
}

// Timer interrupt, every loop period
void control_loop() {
    Inputs inputs = {left_motor.ticks(), right_motor.ticks(), read_vbat(),
                     read_emergency_stop()};
    Outputs outputs = controller.step(inputs);
    left_motor.set_voltage(outputs.u_left, inputs.vbat);
    right_motor.set_voltage(outputs.u_right, inputs.vbat);

    TraceSample sample;
    if (controller.trace_sample(sample)) {
        sample_msg.time_ms = sample.time_ms;
        sample_msg.setpoint = sample.setpoint;
        sample_msg.measurement = sample.measurement;
        sample_msg.u_left = sample.u_left;
        sample_msg.u_right = sample.u_right;
        sample_msg.vbat = sample.vbat;
        sample_ready = true;
    }

    TraceEnd end;
    if (controller.take_trace_end(end)) {
        trace_end_msg.sample_count = end.sample_count;
        trace_end_msg.state = (byte)end.state;
        trace_end_msg.ts = end.ts;
        trace_end_msg.kp = end.kp;
        trace_end_msg.ki = end.ki;
        trace_end_ready = true;
    }

    // fixed rate, whatever loop() is doing (architecture 2 and 6.1)
    periods_since_status++;
    if (periods_since_status * controller.period() >= STATUS_PERIOD - 1e-9) {
        periods_since_status = 0;
        Status status = controller.status();
        status_msg.move_id = status.move_id;
        status_msg.state = (byte)status.state;
        status_msg.flags = status.flags | HARDWARE_FLAGS;
        status_msg.x = status.pose.x;
        status_msg.y = status.pose.y;
        status_msg.theta = status.pose.theta;
        status_msg.v = status.v;
        status_msg.omega = status.omega;
        status_msg.vbat = status.vbat;
        status_msg.time_ms = millis();
        status_msg.boot_id = boot_id;
        status_msg.heartbeat = last_heartbeat;
        status_ready = true;
    }
}

// Copies a received message, false if its size is wrong
template <typename T>
bool read_message(const byte* data, byte size, T& message) {
    if (size != sizeof(T)) {
        return false;
    }
    memcpy(&message, data, sizeof(T));
    return true;
}

// Callbacks of the messages of the Pi

void on_move(byte* data, byte size) {
    msg_move message;
    if (!read_message(data, size, message)) {
        return;
    }
    MoveCommand command;
    command.id = message.move_id;
    command.kind = (MoveKind)message.kind;
    command.flags = message.flags;
    command.x = message.x;
    command.y = message.y;
    command.theta = message.theta;
    command.distance = message.distance;
    command.max_speed = message.max_speed;
    command.max_accel = message.max_accel;
    // refused: move_id does not change in the status
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        controller.move(command);
    }
}

void on_set_control_params(byte* data, byte size) {
    msg_set_control_params message;
    if (!read_message(data, size, message)) {
        return;
    }
    Param param = (Param)message.param;
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        if (controller.set_param(param, message.value) &&
            param == Param::LOOP_PERIOD) {
            Timer1.setPeriod(lround(message.value * 1e6));
        }
    }
}

void on_reset_pose(byte* data, byte size) {
    msg_reset_pose message;
    if (!read_message(data, size, message)) {
        return;
    }
    // refused while moving: the Pi checks the pose in the next status
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        controller.reset_pose({message.x, message.y, message.theta});
    }
}

void on_stop(byte* data, byte size) {
    msg_stop message;
    if (!read_message(data, size, message)) {
        return;
    }
    StopMode mode = message.mode == (byte)StopMode::URGENT ? StopMode::URGENT
                                                           : StopMode::SMOOTH;
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        controller.stop(mode);
    }
}

void on_start_trace(byte* data, byte size) {
    msg_start_trace message;
    if (!read_message(data, size, message)) {
        return;
    }
    TraceCommand command;
    command.kind = (TraceKind)message.kind;
    command.loop = (TraceLoop)message.loop;
    command.initial = message.initial;
    command.final_value = message.final;
    command.step_time = message.step_time;
    command.duration = message.duration;
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        controller.start_trace(command);
    }
}

void on_heartbeat(byte* data, byte size) {
    msg_heartbeat message;
    if (!read_message(data, size, message)) {
        return;
    }
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        controller.heartbeat();
        last_heartbeat = message.counter;
    }
}

void on_reset_teensy(byte* data, byte size) {
    // software reset of the Cortex-M7: the boot_id changes
    SCB_AIRCR = 0x05FA0004;
}

void (*callbacks[256])(byte* msg, byte size);

void setup() {
    // drivers stopped first (R8)
    analogWriteFrequency(R_PWM, PWM_FREQUENCY);
    analogWriteFrequency(L_PWM, PWM_FREQUENCY);
    analogWriteResolution(PWM_RESOLUTION);
    left_motor.init();
    right_motor.init();

#ifdef ESTOP_PIN
    pinMode(ESTOP_PIN, INPUT);
#endif

    // random, so that the Pi sees a restart of the Teensy (pose lost)
    Entropy.Initialize();
    boot_id = Entropy.random();

    com = new Com(&Serial, BAUDRATE);
    callbacks[MOVE] = &on_move;
    callbacks[SET_CONTROL_PARAMS] = &on_set_control_params;
    callbacks[RESET_POSE] = &on_reset_pose;
    callbacks[STOP] = &on_stop;
    callbacks[START_TRACE] = &on_start_trace;
    callbacks[HEARTBEAT] = &on_heartbeat;
    callbacks[RESET_TEENSY] = &on_reset_teensy;

    Timer1.initialize(lround(LOOP_PERIOD_DEFAULT * 1e6));
    Timer1.attachInterrupt(control_loop);
}

// Sends a message prepared by the timer; the copy keeps the timer from
// changing it while it is sent
template <typename T>
void send_prepared(T& message, volatile bool& ready) {
    if (!ready) {
        return;
    }
    T copy;
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        copy = message;
        ready = false;
    }
    com->send_msg((byte*)&copy, sizeof(T));
}

void loop() {
    com->handle_callback(callbacks);

    send_prepared(sample_msg, sample_ready);
    send_prepared(trace_end_msg, trace_end_ready);
    send_prepared(status_msg, status_ready);
}
