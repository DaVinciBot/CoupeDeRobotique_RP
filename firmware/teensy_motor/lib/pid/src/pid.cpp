#include "pid.h"
#include <math.h>

PID::PID(double kp, double ki, double minOutput, double maxOutput, double ts)
    : _kp(kp),
      _ki(ki),
      _minOutput(minOutput),
      _maxOutput(maxOutput),
      _integral(0.0),
      _ts(ts) {}

void PID::setTunings(double kp, double ki) {
    this->_kp = kp;
    this->_ki = ki;
}

void PID::setOutputLimits(double minOutput, double maxOutput) {
    if (minOutput >= maxOutput) {
        return;  // invalid limits: the old ones are kept
    }
    this->_minOutput = minOutput;
    this->_maxOutput = maxOutput;
}

void PID::setPeriod(double ts) {
    this->_ts = ts;
}

void PID::reset() {
    this->_integral = 0.0;
}

double PID::compute(double error, double limit) {
    double max_output = fmin(this->_maxOutput, limit);
    double min_output = fmax(this->_minOutput, -limit);

    // immediate correction + accumulated correction
    double output = this->_kp * error + this->_integral;

    // saturated output: return the limit without integrating, so that the
    // integral does not grow forever when a wheel is blocked
    if (output > max_output) {
        return max_output;
    }
    if (output < min_output) {
        return min_output;
    }

    // not saturated: the error is accumulated for the next period
    this->_integral += this->_ki * error * this->_ts;
    return output;
}
