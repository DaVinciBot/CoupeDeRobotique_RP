// Motion controller on the simulated rolling base (simulation/plant.h)

#include <math.h>
#include <motion_controller.h>
#include <unity.h>
#include "../../simulation/plant.h"

using namespace motion;

const double DEG = kPi / 180.0;

// Controller + simulated robot; the brain sends a heartbeat every 50 ms
struct Bench {
    MotionController controller{sim::config(), sim::TS};
    sim::Plant plant;
    Outputs last = {0.0, 0.0};
    bool heartbeat = true;
    int periods = 0;

    explicit Bench(bool configure = true) {
        if (configure) {
            TEST_ASSERT_TRUE(this->controller.set_params(sim::params()));
        }
        this->controller.heartbeat();
    }

    void step() {
        if (this->heartbeat && this->periods % 10 == 0) {
            this->controller.heartbeat();
        }
        this->last = this->controller.step(this->plant.inputs());
        this->plant.apply(this->last);
        this->periods++;
    }

    void run_for(double duration) {
        for (int i = 0; i < duration / sim::TS; i++) {
            this->step();
        }
    }

    // Runs until the state is not MOVING; false after timeout
    bool run_until_done(double timeout) {
        for (int i = 0; i < timeout / sim::TS; i++) {
            this->step();
            if (this->controller.status().state != MotionState::MOVING) {
                return true;
            }
        }
        return false;
    }

    MotionState state() const { return this->controller.status().state; }
    Pose pose() const { return this->controller.status().pose; }
};

static MoveCommand goto_command(uint16_t id,
                                double x,
                                double y,
                                uint8_t flags = 0,
                                double theta = 0.0) {
    MoveCommand c;
    c.id = id;
    c.kind = MoveKind::GOTO;
    c.flags = flags;
    c.x = x;
    c.y = y;
    c.theta = theta;
    return c;
}

static MoveCommand simple_command(uint16_t id,
                                  MoveKind kind,
                                  double theta,
                                  double distance) {
    MoveCommand c;
    c.id = id;
    c.kind = kind;
    c.theta = theta;
    c.distance = distance;
    return c;
}

static double angle_gap(double a, double b) {
    return fabs(normalize_angle(a - b));
}

void setUp() {}
void tearDown() {}

// Safety and settings

void test_inert_until_configured() {
    Bench bench(false);
    TEST_ASSERT_FALSE(bench.controller.configured());
    TEST_ASSERT_FALSE(bench.controller.move(goto_command(1, 0.3, 0.0)));

    // all the settings but one: still inert
    sim::Plant plant;
    ControlParams p = sim::params();
    MotionController controller(sim::config(), sim::TS);
    controller.heartbeat();
    controller.set_param(Param::LEFT_SPEED_KP, p.left_speed_kp);
    TEST_ASSERT_FALSE(controller.configured());
    TEST_ASSERT_TRUE(controller.set_params(p));
    TEST_ASSERT_TRUE(controller.configured());
    TEST_ASSERT_TRUE(controller.move(goto_command(1, 0.3, 0.0)));
}

void test_invalid_settings_are_ignored() {
    MotionController controller(sim::config(), sim::TS);
    TEST_ASSERT_FALSE(controller.set_param(Param::LEFT_SPEED_KP, -1.0));
    TEST_ASSERT_FALSE(controller.set_param(Param::MAX_SPEED, 0.0));
    TEST_ASSERT_FALSE(controller.set_param(Param::MAX_SPEED, NAN));
    TEST_ASSERT_FALSE(controller.set_param(Param::PUSH_VOLTAGE, 13.0));
    TEST_ASSERT_FALSE(controller.set_param(Param::LOOP_PERIOD, 0.1));
    TEST_ASSERT_FALSE(controller.set_param(Param::COUNT, 1.0));
    TEST_ASSERT_TRUE(controller.set_param(Param::MAX_SPEED, 0.3));
    TEST_ASSERT_EQUAL_DOUBLE(0.3, controller.params().max_speed);
}

void test_loop_period_refused_while_moving() {
    Bench bench;
    TEST_ASSERT_TRUE(bench.controller.move(goto_command(1, 0.5, 0.0)));
    bench.run_for(0.2);
    TEST_ASSERT_FALSE(bench.controller.set_param(Param::LOOP_PERIOD, 0.002));
}

void test_no_move_without_heartbeat() {
    MotionController controller(sim::config(), sim::TS);
    controller.set_params(sim::params());
    TEST_ASSERT_TRUE(controller.status().flags &
                     status_flags::HEARTBEAT_LOST);
    TEST_ASSERT_FALSE(controller.move(goto_command(1, 0.3, 0.0)));
    controller.heartbeat();
    TEST_ASSERT_TRUE(controller.move(goto_command(1, 0.3, 0.0)));
}

void test_heartbeat_lost_brakes_and_stops() {
    Bench bench;
    bench.controller.move(simple_command(1, MoveKind::STRAIGHT, 0.0, 2.0));
    bench.run_for(2.0);
    TEST_ASSERT_DOUBLE_WITHIN(0.01, 0.2, bench.controller.status().v);

    // the brain goes silent
    bench.heartbeat = false;
    bench.run_for(0.19);
    TEST_ASSERT_EQUAL(MotionState::MOVING, bench.state());
    TEST_ASSERT_TRUE(bench.run_until_done(2.0));
    TEST_ASSERT_EQUAL(MotionState::STOPPED, bench.state());
    TEST_ASSERT_TRUE(bench.controller.status().flags &
                     status_flags::HEARTBEAT_LOST);
    // braking at 0.15 m/s² from 0.2 m/s: about 0.13 m, far from the target
    TEST_ASSERT_TRUE(bench.controller.travelled_distance() < 1.0);
    bench.run_for(0.5);
    TEST_ASSERT_DOUBLE_WITHIN(0.005, 0.0, bench.controller.status().v);
    TEST_ASSERT_FALSE(bench.controller.move(goto_command(2, 0.0, 0.0)));
}

void test_emergency_stop() {
    Bench bench;
    bench.controller.move(simple_command(1, MoveKind::STRAIGHT, 0.0, 1.0));
    bench.run_for(1.0);

    bench.plant.emergency_stop = true;
    bench.step();
    TEST_ASSERT_EQUAL_DOUBLE(0.0, bench.last.u_left);
    TEST_ASSERT_EQUAL_DOUBLE(0.0, bench.last.u_right);
    TEST_ASSERT_EQUAL(MotionState::STOPPED, bench.state());
    TEST_ASSERT_TRUE(bench.controller.status().flags &
                     status_flags::EMERGENCY_STOP);
    TEST_ASSERT_FALSE(bench.controller.move(goto_command(2, 0.0, 0.0)));

    // odometry keeps counting while the robot coasts
    double before = bench.controller.travelled_distance();
    bench.run_for(0.5);
    TEST_ASSERT_TRUE(bench.controller.travelled_distance() > before);

    // re-armed: nothing moves without a new command (R2)
    bench.plant.emergency_stop = false;
    bench.run_for(1.0);
    TEST_ASSERT_EQUAL_DOUBLE(0.0, bench.last.u_left);
    TEST_ASSERT_EQUAL_DOUBLE(0.0, bench.last.u_right);
}

void test_smooth_and_urgent_stop() {
    Bench bench;
    bench.controller.move(simple_command(1, MoveKind::STRAIGHT, 0.0, 2.0));
    bench.run_for(2.0);
    bench.controller.stop(StopMode::SMOOTH);
    bench.step();
    // still braking, motors still powered
    TEST_ASSERT_EQUAL(MotionState::MOVING, bench.state());
    TEST_ASSERT_TRUE(bench.run_until_done(2.0));
    TEST_ASSERT_EQUAL(MotionState::STOPPED, bench.state());

    bench.controller.move(simple_command(2, MoveKind::STRAIGHT, 0.0, 2.0));
    bench.run_for(2.0);
    bench.controller.stop(StopMode::URGENT);
    TEST_ASSERT_EQUAL(MotionState::STOPPED, bench.state());
    bench.step();
    TEST_ASSERT_EQUAL_DOUBLE(0.0, bench.last.u_left);
    TEST_ASSERT_EQUAL_DOUBLE(0.0, bench.last.u_right);
}

// Moves

void test_goto_forward() {
    Bench bench;
    TEST_ASSERT_TRUE(bench.controller.move(
        goto_command(7, 0.5, 0.5, move_flags::HAS_HEADING, kPi / 2)));
    TEST_ASSERT_TRUE(bench.run_until_done(15.0));

    Status status = bench.controller.status();
    TEST_ASSERT_EQUAL(7, status.move_id);
    TEST_ASSERT_EQUAL(MotionState::ARRIVED, status.state);
    TEST_ASSERT_DOUBLE_WITHIN(0.005, 0.5, status.pose.x);
    TEST_ASSERT_DOUBLE_WITHIN(0.005, 0.5, status.pose.y);
    TEST_ASSERT_DOUBLE_WITHIN(0.02, kPi / 2, status.pose.theta);
    // the odometry agrees with the real robot
    TEST_ASSERT_DOUBLE_WITHIN(0.002, bench.plant.pose.x, status.pose.x);
    TEST_ASSERT_DOUBLE_WITHIN(0.002, bench.plant.pose.y, status.pose.y);
}

void test_goto_without_heading_keeps_direction() {
    Bench bench;
    bench.controller.move(goto_command(1, 0.3, 0.3));
    TEST_ASSERT_TRUE(bench.run_until_done(15.0));
    TEST_ASSERT_DOUBLE_WITHIN(0.03, kPi / 4, bench.pose().theta);
}

void test_goto_reverse() {
    Bench bench;
    // target behind the robot: it backs up without turning round
    bench.controller.move(goto_command(1, -0.4, 0.0, move_flags::REVERSE));
    double min_speed = 0.0;
    for (int i = 0; i < 2000 && bench.state() == MotionState::MOVING; i++) {
        bench.step();
        min_speed = fmin(min_speed, bench.controller.status().v);
    }
    TEST_ASSERT_EQUAL(MotionState::ARRIVED, bench.state());
    TEST_ASSERT_DOUBLE_WITHIN(0.005, -0.4, bench.pose().x);
    TEST_ASSERT_TRUE(angle_gap(bench.pose().theta, 0.0) < 0.02);
    TEST_ASSERT_TRUE(min_speed < -0.15);
}

void test_rotate_by_and_to() {
    Bench bench;
    bench.controller.move(simple_command(1, MoveKind::ROTATE_BY, kPi / 2, 0.0));
    TEST_ASSERT_TRUE(bench.run_until_done(10.0));
    TEST_ASSERT_TRUE(angle_gap(bench.pose().theta, kPi / 2) < 0.02);
    // rotation on the spot
    TEST_ASSERT_DOUBLE_WITHIN(0.003, 0.0, bench.pose().x);

    bench.controller.move(simple_command(2, MoveKind::ROTATE_TO, -kPi / 4, 0.0));
    TEST_ASSERT_TRUE(bench.run_until_done(10.0));
    TEST_ASSERT_EQUAL(MotionState::ARRIVED, bench.state());
    TEST_ASSERT_TRUE(angle_gap(bench.pose().theta, -kPi / 4) < 0.02);
}

void test_straight_backwards() {
    Bench bench;
    bench.controller.move(simple_command(1, MoveKind::STRAIGHT, 0.0, -0.25));
    TEST_ASSERT_TRUE(bench.run_until_done(10.0));
    TEST_ASSERT_DOUBLE_WITHIN(0.004, -0.25, bench.pose().x);
}

void test_max_speed_of_the_command() {
    Bench bench;
    MoveCommand c = simple_command(1, MoveKind::STRAIGHT, 0.0, 1.0);
    c.max_speed = 0.1;
    bench.controller.move(c);
    bench.run_for(3.0);
    TEST_ASSERT_DOUBLE_WITHIN(0.01, 0.1, bench.controller.status().v);

    // above the configured limit: the configured limit wins
    Bench fast;
    c.max_speed = 5.0;
    fast.controller.move(c);
    fast.run_for(3.0);
    TEST_ASSERT_DOUBLE_WITHIN(0.01, 0.2, fast.controller.status().v);
}

void test_new_goto_slows_down_without_stopping() {
    Bench bench;
    MoveCommand c = goto_command(1, 1.5, 0.0);
    bench.controller.move(c);
    bench.run_for(3.0);
    TEST_ASSERT_DOUBLE_WITHIN(0.01, 0.2, bench.controller.status().v);

    // same target, lower speed (avoidance slow down)
    c.id = 2;
    c.max_speed = 0.08;
    TEST_ASSERT_TRUE(bench.controller.move(c));
    double min_speed = 1.0;
    for (int i = 0; i < 400; i++) {
        bench.step();
        min_speed = fmin(min_speed, bench.controller.status().v);
    }
    TEST_ASSERT_TRUE(min_speed > 0.07);
    TEST_ASSERT_DOUBLE_WITHIN(0.01, 0.08, bench.controller.status().v);
    TEST_ASSERT_TRUE(bench.run_until_done(20.0));
    TEST_ASSERT_EQUAL(2, bench.controller.status().move_id);
    TEST_ASSERT_DOUBLE_WITHIN(0.005, 1.5, bench.pose().x);
}

void test_new_move_in_other_direction_brakes_first() {
    Bench bench;
    bench.controller.move(simple_command(1, MoveKind::STRAIGHT, 0.0, 1.0));
    bench.run_for(2.0);

    // a target behind: the robot must stop before turning
    bench.controller.move(goto_command(2, 0.0, 0.5));
    double max_omega = 0.0;
    double v_when_turning = 0.0;
    for (int i = 0; i < 4000 && bench.state() == MotionState::MOVING; i++) {
        bench.step();
        Status s = bench.controller.status();
        if (fabs(s.omega) > max_omega) {
            max_omega = fabs(s.omega);
            v_when_turning = s.v;
        }
    }
    TEST_ASSERT_EQUAL(MotionState::ARRIVED, bench.state());
    TEST_ASSERT_DOUBLE_WITHIN(0.02, 0.0, v_when_turning);
    TEST_ASSERT_DOUBLE_WITHIN(0.005, 0.0, bench.pose().x);
    TEST_ASSERT_DOUBLE_WITHIN(0.005, 0.5, bench.pose().y);
}

void test_blocked_wheel() {
    Bench bench;
    bench.controller.move(simple_command(1, MoveKind::STRAIGHT, 0.0, 1.0));
    bench.run_for(1.0);
    bench.plant.left.blocked = true;
    TEST_ASSERT_TRUE(bench.run_until_done(3.0));
    TEST_ASSERT_EQUAL(MotionState::BLOCKED, bench.state());
    bench.step();
    TEST_ASSERT_EQUAL_DOUBLE(0.0, bench.last.u_left);
    TEST_ASSERT_EQUAL_DOUBLE(0.0, bench.last.u_right);
}

void test_reset_pose() {
    Bench bench;
    bench.controller.move(simple_command(1, MoveKind::STRAIGHT, 0.0, 0.5));
    bench.run_for(0.5);
    Pose wrong = {1.0, 1.0, 1.0};
    TEST_ASSERT_FALSE(bench.controller.reset_pose(wrong));

    TEST_ASSERT_TRUE(bench.run_until_done(10.0));
    double distance = bench.controller.travelled_distance();
    Pose pose = {1.0, 0.5, 3 * kPi};
    TEST_ASSERT_TRUE(bench.controller.reset_pose(pose));
    TEST_ASSERT_DOUBLE_WITHIN(1e-9, kPi, fabs(bench.pose().theta));
    // the loops do not see the jump
    bench.run_for(0.5);
    TEST_ASSERT_DOUBLE_WITHIN(0.001, distance,
                              bench.controller.travelled_distance());
    TEST_ASSERT_TRUE(fabs(bench.last.u_left) < 2.0);
}

void test_push_without_border_ends_arrived() {
    Bench bench;
    MoveCommand c = simple_command(1, MoveKind::PUSH_UNTIL_BLOCKED, 0.0, -0.1);
    c.max_speed = 0.05;
    bench.controller.move(c);
    TEST_ASSERT_TRUE(bench.run_until_done(10.0));
    TEST_ASSERT_EQUAL(MotionState::ARRIVED, bench.state());
    TEST_ASSERT_DOUBLE_WITHIN(0.01, -0.1, bench.pose().x);
}

void test_push_against_border() {
    Bench bench;
    bench.plant.walls = true;
    // the rear faces the border y = 0, about 3° off
    bench.plant.pose = {0.5, 0.2, kPi / 2 + 0.05};
    bench.controller.reset_pose({0.5, 0.2, kPi / 2});
    MoveCommand c = simple_command(1, MoveKind::PUSH_UNTIL_BLOCKED, 0.0, -0.4);
    c.max_speed = 0.05;
    bench.controller.move(c);
    TEST_ASSERT_TRUE(bench.run_until_done(20.0));
    TEST_ASSERT_EQUAL(MotionState::BLOCKED, bench.state());
    // both corners on the border: the robot is flat against it
    TEST_ASSERT_TRUE(angle_gap(bench.plant.pose.theta, kPi / 2) < 0.2 * DEG);
    TEST_ASSERT_DOUBLE_WITHIN(0.002, sim::D_BACK, bench.plant.pose.y);
}

// Recalibration against two borders, as during the preparation
void test_recalibration_against_two_borders() {
    Bench bench;
    bench.plant.walls = true;
    bench.plant.pose = {0.30, 0.22, kPi / 2 + 0.05};
    // what the robot believes: 3 cm and 3° off
    bench.controller.reset_pose({0.27, 0.25, kPi / 2});

    MoveCommand push = simple_command(1, MoveKind::PUSH_UNTIL_BLOCKED, 0.0, -0.4);
    push.max_speed = 0.05;
    bench.controller.move(push);
    TEST_ASSERT_TRUE(bench.run_until_done(20.0));
    TEST_ASSERT_EQUAL(MotionState::BLOCKED, bench.state());
    // y and theta given by the border, x kept
    TEST_ASSERT_TRUE(
        bench.controller.reset_pose({bench.pose().x, sim::D_BACK, kPi / 2}));

    bench.controller.move(goto_command(2, bench.pose().x, sim::D_BACK + 0.08,
                                       move_flags::HAS_HEADING, 0.0));
    TEST_ASSERT_TRUE(bench.run_until_done(20.0));
    push.id = 3;
    bench.controller.move(push);
    TEST_ASSERT_TRUE(bench.run_until_done(20.0));
    TEST_ASSERT_EQUAL(MotionState::BLOCKED, bench.state());
    // x and theta given by the border, y kept
    TEST_ASSERT_TRUE(
        bench.controller.reset_pose({sim::D_BACK, bench.pose().y, 0.0}));

    Pose believed = bench.pose();
    TEST_ASSERT_DOUBLE_WITHIN(0.001, bench.plant.pose.x, believed.x);
    TEST_ASSERT_DOUBLE_WITHIN(0.001, bench.plant.pose.y, believed.y);
    TEST_ASSERT_TRUE(angle_gap(believed.theta, bench.plant.pose.theta) <
                     0.1 * DEG);
    // well under the 30 s of the architecture
    TEST_ASSERT_TRUE(bench.periods * sim::TS < 30.0);
}

// Traces

void test_open_loop_trace() {
    Bench bench;
    TraceCommand trace;
    trace.kind = TraceKind::OPEN_LOOP_STEP;
    trace.loop = TraceLoop::LEFT_SPEED;
    trace.initial = 3.0;
    trace.final_value = 5.0;
    trace.step_time = 1.0;
    trace.duration = 2.0;
    TEST_ASSERT_TRUE(bench.controller.start_trace(trace));
    TEST_ASSERT_TRUE(bench.controller.status().flags &
                     status_flags::TRACE_RUNNING);

    int samples = 0;
    TraceSample sample;
    double speed_before_step = 0.0;
    while (bench.state() == MotionState::MOVING && samples < 1000) {
        bench.step();
        if (bench.controller.trace_sample(sample)) {
            samples++;
            if (sample.time_ms == 995) {
                speed_before_step = sample.measurement;
            }
        }
    }
    TEST_ASSERT_EQUAL(400, samples);
    TEST_ASSERT_EQUAL_DOUBLE(5.0, sample.setpoint);
    TEST_ASSERT_EQUAL_DOUBLE(5.0, sample.u_left);
    // K * (u - dead zone), reached after 10 tau; the speed measured over one
    // period is known to one encoder count (about 9 mm/s)
    const double count_speed = sim::TICK_DISTANCE / sim::TS;
    TEST_ASSERT_DOUBLE_WITHIN(count_speed, sim::K_LEFT * 2.0,
                              speed_before_step);
    TEST_ASSERT_DOUBLE_WITHIN(count_speed, sim::K_LEFT * 4.0,
                              sample.measurement);

    TraceEnd end;
    TEST_ASSERT_TRUE(bench.controller.take_trace_end(end));
    TEST_ASSERT_FALSE(bench.controller.take_trace_end(end));
    TEST_ASSERT_EQUAL(400, end.sample_count);
    TEST_ASSERT_EQUAL(MotionState::ARRIVED, end.state);
    bench.step();
    TEST_ASSERT_EQUAL_DOUBLE(0.0, bench.last.u_left);
}

void test_closed_loop_speed_trace() {
    Bench bench;
    TraceCommand trace;
    trace.kind = TraceKind::CLOSED_LOOP_STEP;
    trace.loop = TraceLoop::RIGHT_SPEED;
    trace.initial = 0.05;
    trace.final_value = 0.1;
    trace.step_time = 0.5;
    trace.duration = 1.0;
    TEST_ASSERT_TRUE(bench.controller.start_trace(trace));
    TraceSample sample;
    while (bench.state() == MotionState::MOVING) {
        bench.step();
        bench.controller.trace_sample(sample);
    }
    TEST_ASSERT_DOUBLE_WITHIN(0.005, 0.1, sample.measurement);
    TraceEnd end;
    TEST_ASSERT_TRUE(bench.controller.take_trace_end(end));
    TEST_ASSERT_EQUAL_DOUBLE(sim::params().right_speed_kp, end.kp);
    TEST_ASSERT_EQUAL_DOUBLE(sim::params().right_speed_ki, end.ki);
}

void test_invalid_traces_are_refused() {
    Bench bench;
    TraceCommand trace;
    trace.kind = TraceKind::OPEN_LOOP_STEP;
    trace.final_value = 13.0;
    trace.duration = 1.0;
    TEST_ASSERT_FALSE(bench.controller.start_trace(trace));
    trace.final_value = 3.0;
    trace.duration = 11.0;
    TEST_ASSERT_FALSE(bench.controller.start_trace(trace));
    trace.duration = 1.0;
    trace.loop = TraceLoop::DISTANCE;
    TEST_ASSERT_FALSE(bench.controller.start_trace(trace));

    bench.controller.move(simple_command(1, MoveKind::STRAIGHT, 0.0, 0.5));
    trace.loop = TraceLoop::LEFT_SPEED;
    TEST_ASSERT_FALSE(bench.controller.start_trace(trace));
}

void test_stop_ends_the_trace() {
    Bench bench;
    TraceCommand trace;
    trace.kind = TraceKind::OPEN_LOOP_STEP;
    trace.final_value = 4.0;
    trace.duration = 5.0;
    bench.controller.start_trace(trace);
    bench.run_for(0.5);
    bench.controller.stop(StopMode::SMOOTH);
    TraceEnd end;
    TEST_ASSERT_TRUE(bench.controller.take_trace_end(end));
    TEST_ASSERT_EQUAL(MotionState::STOPPED, end.state);
    bench.step();
    TEST_ASSERT_EQUAL_DOUBLE(0.0, bench.last.u_left);
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_inert_until_configured);
    RUN_TEST(test_invalid_settings_are_ignored);
    RUN_TEST(test_loop_period_refused_while_moving);
    RUN_TEST(test_no_move_without_heartbeat);
    RUN_TEST(test_heartbeat_lost_brakes_and_stops);
    RUN_TEST(test_emergency_stop);
    RUN_TEST(test_smooth_and_urgent_stop);
    RUN_TEST(test_goto_forward);
    RUN_TEST(test_goto_without_heading_keeps_direction);
    RUN_TEST(test_goto_reverse);
    RUN_TEST(test_rotate_by_and_to);
    RUN_TEST(test_straight_backwards);
    RUN_TEST(test_max_speed_of_the_command);
    RUN_TEST(test_new_goto_slows_down_without_stopping);
    RUN_TEST(test_new_move_in_other_direction_brakes_first);
    RUN_TEST(test_blocked_wheel);
    RUN_TEST(test_reset_pose);
    RUN_TEST(test_push_without_border_ends_arrived);
    RUN_TEST(test_push_against_border);
    RUN_TEST(test_recalibration_against_two_borders);
    RUN_TEST(test_open_loop_trace);
    RUN_TEST(test_closed_loop_speed_trace);
    RUN_TEST(test_invalid_traces_are_refused);
    RUN_TEST(test_stop_ends_the_trace);
    return UNITY_END();
}
