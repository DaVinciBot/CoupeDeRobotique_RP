/**
 * Control of the rolling base, without any hardware access.
 *
 * The same code runs on the Teensy (called by the loop timer), in the native
 * tests and in the simulation. Units are SI: m, rad, s, m/s, rad/s, V.
 * Messages and behaviour: docs/adr/0003-motion-protocol.md.
 *
 * The methods are not thread safe: on the Teensy, the caller blocks the
 * timer interrupt around every call made outside of it.
 */

#ifndef MOTION_CONTROLLER_H
#define MOTION_CONTROLLER_H

#include <pid.h>
#include <stdint.h>
#include <trapezoid.h>

namespace motion {

constexpr double kPi = 3.14159265358979323846;

/**
 * @brief Angle brought back to [-pi, pi)
 */
double normalize_angle(double theta);

/**
 * @brief Number of loop periods needed to cover a duration (s)
 *
 * The period comes from the brain as a float (0.005 is 0.00499999989): a
 * thousandth of a period is ignored, so that 50 ms are 10 periods of 5 ms.
 */
uint32_t periods_in(double duration, double ts);

enum class MoveKind : uint8_t {
    ROTATE_BY = 0,
    ROTATE_TO = 1,
    STRAIGHT = 2,
    GOTO = 3,
    PUSH_UNTIL_BLOCKED = 4,
};

enum class MotionState : uint8_t {
    MOVING = 0,
    ARRIVED = 1,
    BLOCKED = 2,
    STOPPED = 3,
};

enum class StopMode : uint8_t { SMOOTH = 0, URGENT = 1 };

enum class TraceKind : uint8_t { OPEN_LOOP_STEP = 0, CLOSED_LOOP_STEP = 1 };

enum class TraceLoop : uint8_t {
    LEFT_SPEED = 0,
    RIGHT_SPEED = 1,
    DISTANCE = 2,
    HEADING = 3,
};

// Settings sent by the brain at start-up, one per SET_CONTROL_PARAMS
enum class Param : uint8_t {
    LEFT_SPEED_KP = 0,       // V/(m/s)
    LEFT_SPEED_KI = 1,       // V/m
    RIGHT_SPEED_KP = 2,      // V/(m/s)
    RIGHT_SPEED_KI = 3,      // V/m
    DISTANCE_KP = 4,         // 1/s
    HEADING_KP = 5,          // 1/s
    MAX_SPEED = 6,           // m/s
    MAX_ACCEL = 7,           // m/s²
    MAX_ANGULAR_SPEED = 8,   // rad/s
    MAX_ANGULAR_ACCEL = 9,   // rad/s²
    POSITION_TOLERANCE = 10,  // m
    ANGLE_TOLERANCE = 11,    // rad
    BLOCK_VOLTAGE = 12,      // V
    BLOCK_SPEED = 13,        // m/s
    BLOCK_TIME = 14,         // s
    PUSH_VOLTAGE = 15,       // V
    LOOP_PERIOD = 16,        // s
    COUNT = 17,
};

namespace move_flags {
constexpr uint8_t REVERSE = 1 << 0;      // GOTO backwards
constexpr uint8_t HAS_HEADING = 1 << 1;  // GOTO with a final heading
}  // namespace move_flags

namespace status_flags {
constexpr uint8_t CONFIGURED = 1 << 0;
constexpr uint8_t EMERGENCY_STOP = 1 << 1;
constexpr uint8_t HEARTBEAT_LOST = 1 << 2;
constexpr uint8_t VBAT_MISSING = 1 << 3;          // set by the hardware layer
constexpr uint8_t ESTOP_SENSOR_MISSING = 1 << 4;  // set by the hardware layer
constexpr uint8_t TRACE_RUNNING = 1 << 5;
}  // namespace status_flags

struct Pose {
    double x = 0.0;      // m
    double y = 0.0;      // m
    double theta = 0.0;  // rad
};

// Fixed by the hardware and the safety rules, never sent by the brain
struct Config {
    double tick_distance;       // distance per encoder count, m
    double track_width;         // distance between the encoder wheels, m
    double u_max;               // motor voltage limit, V
    double heartbeat_timeout;   // s
    double max_trace_duration;  // s
    double continue_angle;      // heading gap under which a GOTO goes on, rad
};

struct ControlParams {
    double left_speed_kp, left_speed_ki;
    double right_speed_kp, right_speed_ki;
    double distance_kp, heading_kp;
    double max_speed, max_accel;
    double max_angular_speed, max_angular_accel;
    double position_tolerance, angle_tolerance;
    double block_voltage, block_speed, block_time;
    double push_voltage;
    double loop_period;
};

struct MoveCommand {
    uint16_t id = 0;
    MoveKind kind = MoveKind::STRAIGHT;
    uint8_t flags = 0;
    double x = 0.0, y = 0.0, theta = 0.0;  // m, m, rad
    double distance = 0.0;                 // m, signed
    double max_speed = 0.0;                // m/s, 0 = configured limit
    double max_accel = 0.0;                // m/s², 0 = configured limit
};

struct TraceCommand {
    TraceKind kind = TraceKind::OPEN_LOOP_STEP;
    TraceLoop loop = TraceLoop::LEFT_SPEED;
    double initial = 0.0;      // V, m/s, m or rad, before step_time
    double final_value = 0.0;  // same unit, from step_time
    double step_time = 0.0;    // s
    double duration = 0.0;     // s
};

// What the hardware gives at each period
struct Inputs {
    int32_t left_ticks;   // encoder count since start-up
    int32_t right_ticks;  // encoder count since start-up
    double vbat;          // V
    bool emergency_stop;  // power cut by the emergency stop button
};

// Voltages to apply, already limited to u_max and vbat
struct Outputs {
    double u_left;
    double u_right;
};

struct Status {
    uint16_t move_id;
    MotionState state;
    uint8_t flags;
    Pose pose;
    double v;      // m/s
    double omega;  // rad/s
    double vbat;   // V
};

struct TraceSample {
    uint32_t time_ms;  // since the start of the trace
    double setpoint;
    double measurement;
    double u_left, u_right, vbat;
};

struct TraceEnd {
    uint16_t sample_count;
    MotionState state;
    double ts, kp, ki;  // settings used by the loop of the trace
};

class MotionController {
   public:
    MotionController(const Config& config, double ts);

    /**
     * @brief Changes one setting; false if the value is not valid
     *
     * LOOP_PERIOD is refused while moving: the caller must also change the
     * timer period when it is accepted.
     */
    bool set_param(Param param, double value);

    /**
     * @brief Sets all the settings at once (tests and simulation)
     */
    bool set_params(const ControlParams& params);

    const ControlParams& params() const { return this->p; }
    double period() const { return this->ts; }

    // True once every setting has been received at least once
    bool configured() const;

    /**
     * @brief Starts a move, or replaces the current one
     *
     * Refused (false) if not configured, without heartbeat, during an
     * emergency stop or if the command is not valid.
     */
    bool move(const MoveCommand& command);

    void stop(StopMode mode);

    /**
     * @brief Sets the absolute pose; refused (false) while moving
     *
     * Only the pose changes: the loops follow the travelled distance and
     * angle, which never jump.
     */
    bool reset_pose(const Pose& pose);

    void heartbeat();

    /**
     * @brief Starts a control test; refused (false) while moving, if not
     * configured, without heartbeat, during an emergency stop or if the
     * command is not valid
     */
    bool start_trace(const TraceCommand& command);

    /**
     * @brief One loop period: odometry, safety, then the motor voltages
     */
    Outputs step(const Inputs& inputs);

    Status status() const;

    // True if the last step() produced a trace sample
    bool trace_sample(TraceSample& sample) const;

    // True once, after the step() that ended a trace
    bool take_trace_end(TraceEnd& end);

    // Internal values, read by the simulation and the tests
    double travelled_distance() const { return this->delta_mes; }
    double travelled_angle() const { return this->psi_mes; }
    double distance_setpoint() const { return this->delta_profile.position; }
    double angle_setpoint() const { return this->psi_profile.position; }
    double left_speed() const { return this->v_left; }
    double right_speed() const { return this->v_right; }
    double left_speed_target() const { return this->v_left_target; }
    double right_speed_target() const { return this->v_right_target; }

   private:
    enum class Mode { IDLE, POSITION, PUSH, TRACE };
    enum class Step { NONE, BRAKE, ROTATE_TO_TARGET, FORWARD, ROTATE_FINAL };

    Config config;
    double ts;
    ControlParams p = {};
    uint32_t received = 0;  // one bit per Param

    PID left_pid, right_pid;          // output: V
    PID distance_pid, heading_pid;    // output: m/s, rad/s
    Trapezoid delta_profile;          // m
    Trapezoid psi_profile;            // rad

    // Odometry
    bool odometry_started = false;
    int32_t last_left_ticks = 0, last_right_ticks = 0;
    double v_left = 0.0, v_right = 0.0;  // wheel speeds, m/s
    double delta_mes = 0.0;  // travelled distance, m, never reset
    double psi_mes = 0.0;    // travelled angle, rad, never reset
    Pose pose;               // absolute pose, set by reset_pose()
    double v = 0.0, omega = 0.0;
    double vbat = 0.0;

    // Command
    Mode mode = Mode::IDLE;
    Step move_step = Step::NONE;
    MoveCommand current;   // move being done, or waiting for the end of BRAKE
    bool pending = false;  // after BRAKE: start current (true) or stop (false)
    double move_speed = 0.0, move_accel = 0.0;  // limits of the current move
    uint16_t move_id = 0;
    MotionState state = MotionState::STOPPED;
    double v_left_target = 0.0, v_right_target = 0.0;
    double u_left = 0.0, u_right = 0.0;
    double push_start = 0.0, push_length = 0.0, push_speed = 0.0;
    uint32_t blocked_count = 0;

    // Safety
    uint32_t periods_without_heartbeat = 0;
    bool heartbeat_lost = true;
    bool emergency_stop = false;

    // Trace
    TraceCommand trace;
    uint32_t trace_periods = 0;
    uint16_t trace_count = 0;
    double trace_delta0 = 0.0, trace_psi0 = 0.0;
    bool sample_ready = false;
    TraceSample sample = {};
    bool trace_end_ready = false;
    TraceEnd trace_end = {};

    void update_odometry(const Inputs& inputs);
    void go_idle();
    void brake();
    void enter_position_mode();
    void begin(const MoveCommand& command);
    bool continue_move(const MoveCommand& command);
    void start_rotation(double angle);
    void start_rotate_to_target();
    void start_forward(double distance);
    double goto_heading(const MoveCommand& command) const;
    double goto_distance(const MoveCommand& command) const;
    void update_move();
    void finish(MotionState result);
    void run_position();
    void run_push();
    void run_trace();
    void end_trace(MotionState result);
    void apply_speed_targets(double limit);
    double voltage_limit(double limit) const;
    bool check_blocked();
};

}  // namespace motion

#endif  // MOTION_CONTROLLER_H
