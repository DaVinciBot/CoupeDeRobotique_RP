#include <math.h>
#include <trapezoid.h>
#include <unity.h>

const double TS = 0.005;

void setUp() {}
void tearDown() {}

// Runs the profile to its end; checks the limits on the way
static int run(Trapezoid& profile, double v_max, double a_max) {
    int steps = 0;
    double last_speed = profile.speed;
    while (!profile.finished() && steps < 100000) {
        profile.step(TS);
        TEST_ASSERT_TRUE(fabs(profile.speed) <= v_max + 1e-9 ||
                         fabs(profile.speed) <= fabs(last_speed) + 1e-9);
        TEST_ASSERT_TRUE(fabs(profile.speed - last_speed) <=
                         a_max * TS + 1e-9);
        last_speed = profile.speed;
        steps++;
    }
    return steps;
}

void test_reaches_target_exactly() {
    Trapezoid profile(0.5, 1.0);
    profile.start(0.2, 1.0);
    run(profile, 0.5, 1.0);
    TEST_ASSERT_DOUBLE_WITHIN(1e-12, 1.2, profile.position);
    TEST_ASSERT_EQUAL_DOUBLE(0.0, profile.speed);
}

void test_backwards() {
    Trapezoid profile(0.5, 1.0);
    profile.start(0.0, -0.3);
    profile.step(TS);
    TEST_ASSERT_TRUE(profile.speed < 0.0);
    run(profile, 0.5, 1.0);
    TEST_ASSERT_DOUBLE_WITHIN(1e-12, -0.3, profile.position);
}

void test_short_distance_is_a_triangle() {
    Trapezoid profile(0.5, 1.0);
    profile.start(0.0, 0.04);
    double peak = 0.0;
    while (!profile.finished()) {
        profile.step(TS);
        peak = fmax(peak, profile.speed);
    }
    // sqrt(a * d) = 0.2 m/s, below v_max
    TEST_ASSERT_DOUBLE_WITHIN(0.01, 0.2, peak);
}

void test_duration_of_a_full_trapezoid() {
    Trapezoid profile(0.5, 1.0);
    profile.start(0.0, 1.0);
    // 0.5 s to accelerate, 1.5 s of cruise, 0.5 s to brake
    int steps = run(profile, 0.5, 1.0);
    TEST_ASSERT_DOUBLE_WITHIN(2 * TS, 2.5, steps * TS);
}

void test_starts_from_current_speed_without_jump() {
    Trapezoid profile(0.5, 1.0);
    profile.start(0.0, 2.0);
    for (int i = 0; i < 200; i++) {
        profile.step(TS);
    }
    double speed = profile.speed;
    double position = profile.position;

    // new target further away, planned from the current setpoint
    TEST_ASSERT_TRUE(profile.can_reach(1.0));
    profile.start(position, 1.0, speed);
    TEST_ASSERT_EQUAL_DOUBLE(speed, profile.speed);
    profile.step(TS);
    TEST_ASSERT_DOUBLE_WITHIN(1e-9, speed, profile.speed);
    run(profile, 0.5, 1.0);
    TEST_ASSERT_DOUBLE_WITHIN(1e-12, position + 1.0, profile.position);
}

void test_lower_max_speed_slows_down() {
    Trapezoid profile(0.5, 1.0);
    profile.start(0.0, 3.0);
    for (int i = 0; i < 200; i++) {
        profile.step(TS);
    }
    TEST_ASSERT_DOUBLE_WITHIN(1e-9, 0.5, profile.speed);

    profile.set_limits(0.2, 1.0);
    profile.start(profile.position, 1.5, profile.speed);
    // braking down to the new limit, then cruise at 0.2 m/s
    for (int i = 0; i < 100; i++) {
        profile.step(TS);
    }
    TEST_ASSERT_DOUBLE_WITHIN(1e-9, 0.2, profile.speed);
}

void test_can_reach() {
    Trapezoid profile(0.5, 1.0);
    profile.start(0.0, 2.0);
    for (int i = 0; i < 200; i++) {
        profile.step(TS);
    }
    // 0.5 m/s needs 0.125 m to stop
    TEST_ASSERT_TRUE(profile.can_reach(0.2));
    TEST_ASSERT_FALSE(profile.can_reach(0.1));
    TEST_ASSERT_FALSE(profile.can_reach(-0.5));
}

void test_stop_brakes_at_max_acceleration() {
    Trapezoid profile(0.5, 1.0);
    profile.start(0.0, 2.0);
    for (int i = 0; i < 200; i++) {
        profile.step(TS);
    }
    double position = profile.position;
    profile.stop();
    int steps = run(profile, 0.5, 1.0);
    TEST_ASSERT_DOUBLE_WITHIN(1e-9, position + 0.125, profile.position);
    TEST_ASSERT_DOUBLE_WITHIN(2 * TS, 0.5, steps * TS);
}

void test_zero_distance_is_finished_at_once() {
    Trapezoid profile(0.5, 1.0);
    profile.start(0.7, 0.0);
    TEST_ASSERT_TRUE(profile.finished());
    profile.step(TS);
    TEST_ASSERT_EQUAL_DOUBLE(0.7, profile.position);
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_reaches_target_exactly);
    RUN_TEST(test_backwards);
    RUN_TEST(test_short_distance_is_a_triangle);
    RUN_TEST(test_duration_of_a_full_trapezoid);
    RUN_TEST(test_starts_from_current_speed_without_jump);
    RUN_TEST(test_lower_max_speed_slows_down);
    RUN_TEST(test_can_reach);
    RUN_TEST(test_stop_brakes_at_max_acceleration);
    RUN_TEST(test_zero_distance_is_finished_at_once);
    return UNITY_END();
}
