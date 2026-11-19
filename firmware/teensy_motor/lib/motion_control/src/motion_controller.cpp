/**
 * Control of the rolling base (design: docs/asservissement-base-roulante.md).
 *
 * At each period: odometry, safety (emergency stop, heartbeat), then the
 * command of the current mode:
 * - IDLE: motors at 0 V;
 * - POSITION: trapezoids -> P + feedforward on distance and angle ->
 *   split on the wheels -> speed PI of each wheel (cascade, D1 to D8);
 * - PUSH: same speed on both wheels, voltage limited, until blocked;
 * - TRACE: control test (open loop voltage step or closed loop step).
 */

#include "motion_controller.h"
#include <math.h>

namespace motion {

double normalize_angle(double theta) {
    theta = fmod(theta + kPi, 2.0 * kPi);
    if (theta < 0.0) {
        theta += 2.0 * kPi;
    }
    return theta - kPi;
}

namespace {

uint32_t bit(Param param) {
    return 1u << static_cast<uint8_t>(param);
}

constexpr uint32_t ALL_PARAMS =
    (1u << static_cast<uint8_t>(Param::COUNT)) - 1;

double clamp(double value, double limit) {
    return fmax(fmin(value, limit), -limit);
}

}  // namespace

MotionController::MotionController(const Config& config, double ts)
    : config(config),
      ts(ts),
      left_pid(0.0, 0.0, -config.u_max, config.u_max, ts),
      right_pid(0.0, 0.0, -config.u_max, config.u_max, ts),
      distance_pid(0.0, 0.0, 0.0, 0.0, ts),
      heading_pid(0.0, 0.0, 0.0, 0.0, ts),
      delta_profile(1.0, 1.0),
      psi_profile(1.0, 1.0) {}

// Settings

bool MotionController::set_param(Param param, double value) {
    if (!isfinite(value)) {
        return false;
    }

    switch (param) {
        case Param::LEFT_SPEED_KP:
        case Param::LEFT_SPEED_KI:
        case Param::RIGHT_SPEED_KP:
        case Param::RIGHT_SPEED_KI:
        case Param::DISTANCE_KP:
        case Param::HEADING_KP:
            if (value < 0.0) {
                return false;
            }
            break;
        case Param::BLOCK_VOLTAGE:
        case Param::PUSH_VOLTAGE:
            if (value <= 0.0 || value > this->config.u_max) {
                return false;
            }
            break;
        case Param::LOOP_PERIOD:
            if (value < 0.001 || value > 0.02 ||
                this->state == MotionState::MOVING) {
                return false;
            }
            break;
        case Param::COUNT:
            return false;
        default:
            // limits, tolerances and durations
            if (value <= 0.0) {
                return false;
            }
            break;
    }

    switch (param) {
        case Param::LEFT_SPEED_KP:
            this->p.left_speed_kp = value;
            break;
        case Param::LEFT_SPEED_KI:
            this->p.left_speed_ki = value;
            break;
        case Param::RIGHT_SPEED_KP:
            this->p.right_speed_kp = value;
            break;
        case Param::RIGHT_SPEED_KI:
            this->p.right_speed_ki = value;
            break;
        case Param::DISTANCE_KP:
            this->p.distance_kp = value;
            break;
        case Param::HEADING_KP:
            this->p.heading_kp = value;
            break;
        case Param::MAX_SPEED:
            this->p.max_speed = value;
            break;
        case Param::MAX_ACCEL:
            this->p.max_accel = value;
            break;
        case Param::MAX_ANGULAR_SPEED:
            this->p.max_angular_speed = value;
            break;
        case Param::MAX_ANGULAR_ACCEL:
            this->p.max_angular_accel = value;
            break;
        case Param::POSITION_TOLERANCE:
            this->p.position_tolerance = value;
            break;
        case Param::ANGLE_TOLERANCE:
            this->p.angle_tolerance = value;
            break;
        case Param::BLOCK_VOLTAGE:
            this->p.block_voltage = value;
            break;
        case Param::BLOCK_SPEED:
            this->p.block_speed = value;
            break;
        case Param::BLOCK_TIME:
            this->p.block_time = value;
            break;
        case Param::PUSH_VOLTAGE:
            this->p.push_voltage = value;
            break;
        case Param::LOOP_PERIOD:
            this->p.loop_period = value;
            this->ts = value;
            this->left_pid.setPeriod(value);
            this->right_pid.setPeriod(value);
            this->distance_pid.setPeriod(value);
            this->heading_pid.setPeriod(value);
            break;
        case Param::COUNT:
            break;
    }

    // the integral is already multiplied by ki: changing the gains does not
    // make it wrong, so it is kept
    this->left_pid.setTunings(this->p.left_speed_kp, this->p.left_speed_ki);
    this->right_pid.setTunings(this->p.right_speed_kp, this->p.right_speed_ki);
    this->distance_pid.setTunings(this->p.distance_kp, 0.0);
    this->heading_pid.setTunings(this->p.heading_kp, 0.0);
    this->distance_pid.setOutputLimits(-this->p.max_speed, this->p.max_speed);
    this->heading_pid.setOutputLimits(-this->p.max_angular_speed,
                                      this->p.max_angular_speed);

    this->received |= bit(param);
    return true;
}

bool MotionController::set_params(const ControlParams& params) {
    bool ok = true;
    ok &= this->set_param(Param::LEFT_SPEED_KP, params.left_speed_kp);
    ok &= this->set_param(Param::LEFT_SPEED_KI, params.left_speed_ki);
    ok &= this->set_param(Param::RIGHT_SPEED_KP, params.right_speed_kp);
    ok &= this->set_param(Param::RIGHT_SPEED_KI, params.right_speed_ki);
    ok &= this->set_param(Param::DISTANCE_KP, params.distance_kp);
    ok &= this->set_param(Param::HEADING_KP, params.heading_kp);
    ok &= this->set_param(Param::MAX_SPEED, params.max_speed);
    ok &= this->set_param(Param::MAX_ACCEL, params.max_accel);
    ok &= this->set_param(Param::MAX_ANGULAR_SPEED, params.max_angular_speed);
    ok &= this->set_param(Param::MAX_ANGULAR_ACCEL, params.max_angular_accel);
    ok &= this->set_param(Param::POSITION_TOLERANCE, params.position_tolerance);
    ok &= this->set_param(Param::ANGLE_TOLERANCE, params.angle_tolerance);
    ok &= this->set_param(Param::BLOCK_VOLTAGE, params.block_voltage);
    ok &= this->set_param(Param::BLOCK_SPEED, params.block_speed);
    ok &= this->set_param(Param::BLOCK_TIME, params.block_time);
    ok &= this->set_param(Param::PUSH_VOLTAGE, params.push_voltage);
    ok &= this->set_param(Param::LOOP_PERIOD, params.loop_period);
    return ok;
}

bool MotionController::configured() const {
    return (this->received & ALL_PARAMS) == ALL_PARAMS;
}

// Commands

bool MotionController::move(const MoveCommand& command) {
    if (!this->configured() || this->heartbeat_lost || this->emergency_stop) {
        return false;
    }
    if (static_cast<uint8_t>(command.kind) >
        static_cast<uint8_t>(MoveKind::PUSH_UNTIL_BLOCKED)) {
        return false;
    }
    if (!isfinite(command.x) || !isfinite(command.y) ||
        !isfinite(command.theta) || !isfinite(command.distance) ||
        !isfinite(command.max_speed) || !isfinite(command.max_accel)) {
        return false;
    }
    if (command.kind == MoveKind::PUSH_UNTIL_BLOCKED &&
        command.distance == 0.0) {
        return false;
    }

    if (this->mode == Mode::TRACE) {
        this->end_trace(MotionState::STOPPED);
    }

    // the configured limits always win over the ones of the command
    this->move_speed = command.max_speed > 0.0
                           ? fmin(command.max_speed, this->p.max_speed)
                           : this->p.max_speed;
    this->move_accel = command.max_accel > 0.0
                           ? fmin(command.max_accel, this->p.max_accel)
                           : this->p.max_accel;
    this->move_id = command.id;
    this->state = MotionState::MOVING;
    this->blocked_count = 0;

    if (this->mode != Mode::POSITION) {
        this->enter_position_mode();
        this->begin(command);
        return true;
    }

    bool moving =
        this->delta_profile.speed != 0.0 || this->psi_profile.speed != 0.0;
    if (!moving) {
        this->begin(command);
        return true;
    }
    if (this->continue_move(command)) {
        return true;
    }

    // not compatible with the current motion: stop first, then start it
    this->current = command;
    this->pending = true;
    this->move_step = Step::BRAKE;
    this->delta_profile.stop();
    this->psi_profile.stop();
    return true;
}

void MotionController::stop(StopMode mode) {
    if (mode == StopMode::URGENT) {
        if (this->mode == Mode::TRACE) {
            this->end_trace(MotionState::STOPPED);
        }
        this->go_idle();
        if (this->state == MotionState::MOVING) {
            this->state = MotionState::STOPPED;
        }
        return;
    }

    switch (this->mode) {
        case Mode::IDLE:
            return;
        case Mode::PUSH:
            // slow move: cutting the motors is enough
            this->go_idle();
            this->state = MotionState::STOPPED;
            return;
        case Mode::TRACE:
            this->end_trace(MotionState::STOPPED);
            return;
        case Mode::POSITION:
            // already arrived: the robot keeps its position
            if (this->state != MotionState::MOVING) {
                return;
            }
            this->pending = false;
            this->move_step = Step::BRAKE;
            this->delta_profile.stop();
            this->psi_profile.stop();
            return;
    }
}

bool MotionController::reset_pose(const Pose& pose) {
    // the target of the current move was computed with the old pose
    if (this->state == MotionState::MOVING) {
        return false;
    }
    if (!isfinite(pose.x) || !isfinite(pose.y) || !isfinite(pose.theta)) {
        return false;
    }
    this->pose.x = pose.x;
    this->pose.y = pose.y;
    this->pose.theta = normalize_angle(pose.theta);
    return true;
}

void MotionController::heartbeat() {
    this->periods_without_heartbeat = 0;
    this->heartbeat_lost = false;
}

bool MotionController::start_trace(const TraceCommand& command) {
    if (!this->configured() || this->heartbeat_lost || this->emergency_stop ||
        this->state == MotionState::MOVING) {
        return false;
    }
    if (!(command.duration > 0.0 &&
          command.duration <= this->config.max_trace_duration) ||
        !(command.step_time >= 0.0 && command.step_time <= command.duration) ||
        !isfinite(command.initial) || !isfinite(command.final_value)) {
        return false;
    }

    bool speed_loop = command.loop == TraceLoop::LEFT_SPEED ||
                      command.loop == TraceLoop::RIGHT_SPEED;
    switch (command.kind) {
        case TraceKind::OPEN_LOOP_STEP:
            if (!speed_loop || fabs(command.initial) > this->config.u_max ||
                fabs(command.final_value) > this->config.u_max) {
                return false;
            }
            break;
        case TraceKind::CLOSED_LOOP_STEP:
            if (static_cast<uint8_t>(command.loop) >
                static_cast<uint8_t>(TraceLoop::HEADING)) {
                return false;
            }
            if (speed_loop &&
                (fabs(command.initial) > this->p.max_speed ||
                 fabs(command.final_value) > this->p.max_speed)) {
                return false;
            }
            break;
        default:
            return false;
    }

    this->go_idle();
    this->mode = Mode::TRACE;
    this->trace = command;
    this->trace_periods = 0;
    this->trace_count = 0;
    this->trace_delta0 = this->delta_mes;
    this->trace_psi0 = this->psi_mes;
    this->state = MotionState::MOVING;
    return true;
}

// Loop period

Outputs MotionController::step(const Inputs& inputs) {
    this->sample_ready = false;
    this->update_odometry(inputs);
    this->vbat = inputs.vbat;

    // emergency stop (R2): command and integrals to zero, nothing moves
    // again without a new command
    if (inputs.emergency_stop && !this->emergency_stop) {
        if (this->mode == Mode::TRACE) {
            this->end_trace(MotionState::STOPPED);
        }
        this->go_idle();
        if (this->state == MotionState::MOVING) {
            this->state = MotionState::STOPPED;
        }
    }
    this->emergency_stop = inputs.emergency_stop;

    // brain silent: brake and stop (RG H.3, architecture 11.2)
    if (this->periods_without_heartbeat < UINT32_MAX) {
        this->periods_without_heartbeat++;
    }
    if (!this->heartbeat_lost && this->periods_without_heartbeat * this->ts >
                                     this->config.heartbeat_timeout) {
        this->heartbeat_lost = true;
        this->stop(StopMode::SMOOTH);
    }
    // without the brain, nothing stays powered once the robot has stopped
    if (this->heartbeat_lost && this->mode == Mode::POSITION &&
        this->state != MotionState::MOVING) {
        this->go_idle();
    }

    switch (this->mode) {
        case Mode::IDLE:
            this->u_left = 0.0;
            this->u_right = 0.0;
            break;
        case Mode::POSITION:
            this->run_position();
            break;
        case Mode::PUSH:
            this->run_push();
            break;
        case Mode::TRACE:
            this->run_trace();
            break;
    }

    if (this->mode != Mode::IDLE && this->check_blocked()) {
        if (this->mode == Mode::TRACE) {
            this->end_trace(MotionState::BLOCKED);
        } else {
            this->go_idle();
            this->state = MotionState::BLOCKED;
        }
    }

    return {this->u_left, this->u_right};
}

void MotionController::update_odometry(const Inputs& inputs) {
    // the counters do not start at zero: the first period only reads them
    if (!this->odometry_started) {
        this->last_left_ticks = inputs.left_ticks;
        this->last_right_ticks = inputs.right_ticks;
        this->odometry_started = true;
    }

    double d_left =
        (inputs.left_ticks - this->last_left_ticks) * this->config.tick_distance;
    double d_right = (inputs.right_ticks - this->last_right_ticks) *
                     this->config.tick_distance;
    this->last_left_ticks = inputs.left_ticks;
    this->last_right_ticks = inputs.right_ticks;

    this->v_left = d_left / this->ts;
    this->v_right = d_right / this->ts;

    double d = (d_left + d_right) / 2.0;
    double d_theta = (d_right - d_left) / this->config.track_width;

    // travelled distance and angle, followed by the loops
    this->delta_mes += d;
    this->psi_mes += d_theta;

    // absolute pose, in the middle of the arc
    this->pose.x += d * cos(this->pose.theta + d_theta / 2.0);
    this->pose.y += d * sin(this->pose.theta + d_theta / 2.0);
    this->pose.theta = normalize_angle(this->pose.theta + d_theta);

    this->v = d / this->ts;
    this->omega = d_theta / this->ts;
}

void MotionController::go_idle() {
    this->mode = Mode::IDLE;
    this->move_step = Step::NONE;
    this->pending = false;
    this->left_pid.reset();
    this->right_pid.reset();
    this->distance_pid.reset();
    this->heading_pid.reset();
    this->v_left_target = 0.0;
    this->v_right_target = 0.0;
    this->u_left = 0.0;
    this->u_right = 0.0;
    this->blocked_count = 0;
    this->delta_profile.start(this->delta_mes, 0.0);
    this->psi_profile.start(this->psi_mes, 0.0);
}

void MotionController::enter_position_mode() {
    // old integrals would give a jerk at the start
    this->go_idle();
    this->mode = Mode::POSITION;
}

// Moves

void MotionController::begin(const MoveCommand& command) {
    this->current = command;
    this->pending = false;
    this->delta_profile.set_limits(this->move_speed, this->move_accel);
    this->psi_profile.set_limits(this->p.max_angular_speed,
                                 this->p.max_angular_accel);

    switch (command.kind) {
        case MoveKind::ROTATE_BY:
            this->start_rotation(command.theta);
            this->move_step = Step::ROTATE_FINAL;
            break;
        case MoveKind::ROTATE_TO:
            this->start_rotation(
                normalize_angle(command.theta - this->pose.theta));
            this->move_step = Step::ROTATE_FINAL;
            break;
        case MoveKind::STRAIGHT:
            this->start_forward(command.distance);
            break;
        case MoveKind::GOTO:
            this->start_rotate_to_target();
            break;
        case MoveKind::PUSH_UNTIL_BLOCKED:
            this->go_idle();
            this->mode = Mode::PUSH;
            this->push_start = this->delta_mes;
            this->push_length = fabs(command.distance);
            this->push_speed = copysign(this->move_speed, command.distance);
            this->v_left_target = this->push_speed;
            this->v_right_target = this->push_speed;
            break;
    }
}

bool MotionController::continue_move(const MoveCommand& command) {
    if (this->delta_profile.speed != 0.0) {
        // moving straight: only a straight line in the same direction
        if (this->move_step != Step::FORWARD) {
            return false;
        }
        double distance;
        double heading_error = 0.0;
        if (command.kind == MoveKind::STRAIGHT) {
            distance = command.distance;
        } else if (command.kind == MoveKind::GOTO) {
            heading_error = normalize_angle(this->goto_heading(command) -
                                            this->pose.theta);
            if (fabs(heading_error) >= this->config.continue_angle) {
                return false;
            }
            distance = this->goto_distance(command);
        } else {
            return false;
        }

        double d = this->delta_mes + distance - this->delta_profile.position;
        this->delta_profile.set_limits(this->move_speed, this->move_accel);
        if (!this->delta_profile.can_reach(d)) {
            return false;
        }

        this->current = command;
        this->pending = false;
        this->delta_profile.start(this->delta_profile.position, d,
                                  this->delta_profile.speed);
        // small heading gap: corrected while driving
        if (heading_error != 0.0) {
            double d_psi =
                this->psi_mes + heading_error - this->psi_profile.position;
            double w0 = this->psi_profile.can_reach(d_psi)
                            ? this->psi_profile.speed
                            : 0.0;
            this->psi_profile.start(this->psi_profile.position, d_psi, w0);
        }
        return true;
    }

    // rotating in place: only a rotation in the same direction
    if (command.kind != MoveKind::ROTATE_BY &&
        command.kind != MoveKind::ROTATE_TO) {
        return false;
    }
    if (this->move_step != Step::ROTATE_FINAL &&
        this->move_step != Step::ROTATE_TO_TARGET) {
        return false;
    }
    double angle = command.kind == MoveKind::ROTATE_BY
                       ? command.theta
                       : normalize_angle(command.theta - this->pose.theta);
    double d_psi = this->psi_mes + angle - this->psi_profile.position;
    this->psi_profile.set_limits(this->p.max_angular_speed,
                                 this->p.max_angular_accel);
    if (!this->psi_profile.can_reach(d_psi)) {
        return false;
    }

    this->current = command;
    this->pending = false;
    this->psi_profile.start(this->psi_profile.position, d_psi,
                            this->psi_profile.speed);
    this->move_step = Step::ROTATE_FINAL;
    return true;
}

// The targets are taken from the measured distance and angle, and the
// generator goes there from its current setpoint: no jump in the setpoints

void MotionController::start_rotation(double angle) {
    double target = this->psi_mes + angle;
    this->psi_profile.start(this->psi_profile.position,
                            target - this->psi_profile.position,
                            this->psi_profile.speed);
}

void MotionController::start_forward(double distance) {
    double target = this->delta_mes + distance;
    this->delta_profile.start(this->delta_profile.position,
                              target - this->delta_profile.position,
                              this->delta_profile.speed);
    this->move_step = Step::FORWARD;
}

double MotionController::goto_heading(const MoveCommand& command) const {
    double heading =
        atan2(command.y - this->pose.y, command.x - this->pose.x);
    // backwards: the rear of the robot faces the target
    if (command.flags & move_flags::REVERSE) {
        heading += kPi;
    }
    return heading;
}

double MotionController::goto_distance(const MoveCommand& command) const {
    double distance =
        hypot(command.x - this->pose.x, command.y - this->pose.y);
    return (command.flags & move_flags::REVERSE) ? -distance : distance;
}

void MotionController::start_rotate_to_target() {
    if (fabs(this->goto_distance(this->current)) <
        this->p.position_tolerance) {
        if (this->current.flags & move_flags::HAS_HEADING) {
            this->start_rotation(
                normalize_angle(this->current.theta - this->pose.theta));
            this->move_step = Step::ROTATE_FINAL;
        } else {
            this->finish(MotionState::ARRIVED);
        }
        return;
    }
    this->start_rotation(normalize_angle(this->goto_heading(this->current) -
                                         this->pose.theta));
    this->move_step = Step::ROTATE_TO_TARGET;
}

void MotionController::update_move() {
    bool rotation_done =
        this->psi_profile.finished() &&
        fabs(this->psi_profile.position - this->psi_mes) <
            this->p.angle_tolerance;
    bool forward_done =
        this->delta_profile.finished() &&
        fabs(this->delta_profile.position - this->delta_mes) <
            this->p.position_tolerance;

    switch (this->move_step) {
        case Step::NONE:
            break;

        case Step::BRAKE:
            if (this->delta_profile.finished() &&
                this->psi_profile.finished()) {
                if (this->pending) {
                    this->begin(this->current);
                } else {
                    this->finish(MotionState::STOPPED);
                }
            }
            break;

        case Step::ROTATE_TO_TARGET:
            if (rotation_done) {
                // the distance uses the pose reached after the rotation
                this->start_forward(this->goto_distance(this->current));
            }
            break;

        case Step::FORWARD:
            if (forward_done) {
                if (this->current.kind == MoveKind::GOTO &&
                    (this->current.flags & move_flags::HAS_HEADING)) {
                    this->start_rotation(normalize_angle(
                        this->current.theta - this->pose.theta));
                    this->move_step = Step::ROTATE_FINAL;
                } else {
                    this->finish(MotionState::ARRIVED);
                }
            }
            break;

        case Step::ROTATE_FINAL:
            if (rotation_done) {
                this->finish(MotionState::ARRIVED);
            }
            break;
    }
}

void MotionController::finish(MotionState result) {
    // the robot stays controlled on its last setpoint
    this->move_step = Step::NONE;
    this->state = result;
}

// Modes

void MotionController::run_position() {
    this->update_move();

    this->delta_profile.step(this->ts);
    this->psi_profile.step(this->ts);

    // feedforward (planned speed) + correction of the remaining error (7.4)
    double v_c = this->delta_profile.speed +
                 this->distance_pid.compute(this->delta_profile.position -
                                            this->delta_mes);
    double w_c =
        this->psi_profile.speed +
        this->heading_pid.compute(this->psi_profile.position - this->psi_mes);

    // v_c moves both wheels, w_c separates them to turn
    this->v_left_target = v_c - this->config.track_width / 2.0 * w_c;
    this->v_right_target = v_c + this->config.track_width / 2.0 * w_c;

    this->apply_speed_targets(this->config.u_max);
}

void MotionController::run_push() {
    // nothing touched: the brain sees ARRIVED instead of BLOCKED
    if (fabs(this->delta_mes - this->push_start) >= this->push_length) {
        this->go_idle();
        this->state = MotionState::ARRIVED;
        return;
    }
    this->v_left_target = this->push_speed;
    this->v_right_target = this->push_speed;
    this->apply_speed_targets(this->p.push_voltage);
}

void MotionController::run_trace() {
    double t = this->trace_periods * this->ts;
    double value = t >= this->trace.step_time ? this->trace.final_value
                                              : this->trace.initial;
    bool left = this->trace.loop == TraceLoop::LEFT_SPEED;
    double measurement = 0.0;

    if (this->trace.kind == TraceKind::OPEN_LOOP_STEP) {
        double u = clamp(value, this->voltage_limit(this->config.u_max));
        this->u_left = u;
        this->u_right = u;
        measurement = left ? this->v_left : this->v_right;
    } else {
        switch (this->trace.loop) {
            case TraceLoop::LEFT_SPEED:
            case TraceLoop::RIGHT_SPEED:
                // same setpoint on both wheels: the robot goes straight
                this->v_left_target = value;
                this->v_right_target = value;
                measurement = left ? this->v_left : this->v_right;
                break;
            case TraceLoop::DISTANCE:
            case TraceLoop::HEADING: {
                // a step on the setpoint, without trapezoid nor feedforward
                bool distance = this->trace.loop == TraceLoop::DISTANCE;
                double delta_c = this->trace_delta0 + (distance ? value : 0.0);
                double psi_c = this->trace_psi0 + (distance ? 0.0 : value);
                double v_c = this->distance_pid.compute(delta_c - this->delta_mes);
                double w_c = this->heading_pid.compute(psi_c - this->psi_mes);
                this->v_left_target = v_c - this->config.track_width / 2.0 * w_c;
                this->v_right_target = v_c + this->config.track_width / 2.0 * w_c;
                measurement = distance ? this->delta_mes - this->trace_delta0
                                       : this->psi_mes - this->trace_psi0;
                break;
            }
        }
        this->apply_speed_targets(this->config.u_max);
    }

    this->sample.time_ms = (uint32_t)lround(t * 1000.0);
    this->sample.setpoint = value;
    this->sample.measurement = measurement;
    this->sample.u_left = this->u_left;
    this->sample.u_right = this->u_right;
    this->sample.vbat = this->vbat;
    this->sample_ready = true;
    this->trace_count++;

    this->trace_periods++;
    // small margin: the duration is rarely a whole number of periods
    if (this->trace_periods * this->ts >= this->trace.duration - 1e-9) {
        this->end_trace(MotionState::ARRIVED);
    }
}

void MotionController::end_trace(MotionState result) {
    this->trace_end.sample_count = this->trace_count;
    this->trace_end.state = result;
    this->trace_end.ts = this->ts;
    this->trace_end.kp = 0.0;
    this->trace_end.ki = 0.0;
    if (this->trace.kind == TraceKind::CLOSED_LOOP_STEP) {
        switch (this->trace.loop) {
            case TraceLoop::LEFT_SPEED:
                this->trace_end.kp = this->p.left_speed_kp;
                this->trace_end.ki = this->p.left_speed_ki;
                break;
            case TraceLoop::RIGHT_SPEED:
                this->trace_end.kp = this->p.right_speed_kp;
                this->trace_end.ki = this->p.right_speed_ki;
                break;
            case TraceLoop::DISTANCE:
                this->trace_end.kp = this->p.distance_kp;
                break;
            case TraceLoop::HEADING:
                this->trace_end.kp = this->p.heading_kp;
                break;
        }
    }
    this->trace_end_ready = true;
    this->go_idle();
    this->state = result;
}

// Wheels

double MotionController::voltage_limit(double limit) const {
    double result = fmin(limit, this->config.u_max);
    // above vbat, the PWM is already at 100 %
    if (this->vbat > 0.0) {
        result = fmin(result, this->vbat);
    }
    return result;
}

void MotionController::apply_speed_targets(double limit) {
    // the limit is given to the PI, so that it stops integrating there
    double u_limit = this->voltage_limit(limit);
    this->u_left = this->left_pid.compute(
        this->v_left_target - this->v_left, u_limit);
    this->u_right = this->right_pid.compute(
        this->v_right_target - this->v_right, u_limit);
}

bool MotionController::check_blocked() {
    bool pushing = this->mode == Mode::PUSH;
    // while pushing, a wheel that forces stays at the push_voltage limit
    double threshold =
        pushing ? 0.9 * this->p.push_voltage : this->p.block_voltage;

    bool left_blocked = fabs(this->u_left) > threshold &&
                        fabs(this->v_left) < this->p.block_speed;
    bool right_blocked = fabs(this->u_right) > threshold &&
                         fabs(this->v_right) < this->p.block_speed;

    // while pushing, a single blocked wheel means the robot pivots to lie
    // flat against the border: it goes on
    bool blocked =
        pushing ? left_blocked && right_blocked : left_blocked || right_blocked;

    // a hard start does not count: the block must last block_time
    if (!blocked) {
        this->blocked_count = 0;
        return false;
    }
    this->blocked_count++;
    return this->blocked_count >= (uint32_t)ceil(this->p.block_time / this->ts);
}

// Read back

Status MotionController::status() const {
    uint8_t flags = 0;
    if (this->configured()) {
        flags |= status_flags::CONFIGURED;
    }
    if (this->emergency_stop) {
        flags |= status_flags::EMERGENCY_STOP;
    }
    if (this->heartbeat_lost) {
        flags |= status_flags::HEARTBEAT_LOST;
    }
    if (this->mode == Mode::TRACE) {
        flags |= status_flags::TRACE_RUNNING;
    }
    return {this->move_id, this->state, flags, this->pose,
            this->v,       this->omega, this->vbat};
}

bool MotionController::trace_sample(TraceSample& sample) const {
    if (!this->sample_ready) {
        return false;
    }
    sample = this->sample;
    return true;
}

bool MotionController::take_trace_end(TraceEnd& end) {
    if (!this->trace_end_ready) {
        return false;
    }
    end = this->trace_end;
    this->trace_end_ready = false;
    return true;
}

}  // namespace motion
