#include <pid.h>
#include <unity.h>

const double TS = 0.005;

void setUp() {}
void tearDown() {}

void test_proportional_and_integral() {
    PID pid(2.0, 10.0, 0.0, -12.0, 12.0, TS);
    // first call: the integral is still zero
    TEST_ASSERT_DOUBLE_WITHIN(1e-12, 2.0, pid.compute(1.0));
    // then it grows by ki * error * ts per period
    TEST_ASSERT_DOUBLE_WITHIN(1e-12, 2.05, pid.compute(1.0));
}

void test_no_integration_while_saturated() {
    PID pid(1.0, 100.0, 0.0, -12.0, 12.0, TS);
    for (int i = 0; i < 1000; i++) {
        TEST_ASSERT_TRUE(pid.compute(50.0) <= 12.0);
    }
    // saturated from the start: the integral never grew
    TEST_ASSERT_EQUAL_DOUBLE(0.0, pid.compute(0.0));
}

void test_extra_limit_also_stops_integration() {
    PID pid(1.0, 100.0, 0.0, -12.0, 12.0, TS);
    for (int i = 0; i < 1000; i++) {
        TEST_ASSERT_TRUE(pid.compute(2.0, 4.0) <= 4.0);
    }
    // the integral stopped near 4 V: with only the 12 V limit, it would
    // have grown up to 10 V
    TEST_ASSERT_TRUE(pid.compute(0.0) <= 4.0);
}

void test_reset_clears_integral() {
    PID pid(0.0, 10.0, 0.0, -12.0, 12.0, TS);
    pid.compute(1.0);
    pid.compute(1.0);
    pid.reset();
    TEST_ASSERT_EQUAL_DOUBLE(0.0, pid.compute(0.0));
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_proportional_and_integral);
    RUN_TEST(test_no_integration_while_saturated);
    RUN_TEST(test_extra_limit_also_stops_integration);
    RUN_TEST(test_reset_clears_integral);
    return UNITY_END();
}
