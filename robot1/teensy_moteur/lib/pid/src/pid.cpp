/**
 * This is the implementation of the PID class.
 * The PID class compute the error for the servo-control of the motors.
 */

#include "pid.h"
#include <Arduino.h>

PID::PID(double kp,
         double ki,
         double kd,
         double minOutput,
         double maxOutput,
         double deadband,
         double dtMin,
         double dtMax)
    : _kp(kp),
      _ki(ki),
      _kd(kd),
      _minOutput(minOutput),
      _maxOutput(maxOutput),
      _deadband(fabs(deadband)),
      _integral(0.0),
      _prevError(0.0),
      _lastTime(micros()),
      _dtMin(dtMin),
      _dtMax(dtMax) {}

// TODO: réimplémenter les méthodes du PID (cf. doc de Fadi)

void PID::updateParameters(double kp, double ki, double kd) {}

void PID::setTunings(double kp, double ki, double kd) {}

void PID::setOutputLimits(double minOutput, double maxOutput) {}

void PID::setDeadband(double deadband) {}

void PID::reset() {}

double PID::compute(double error) {
    return 0.0;
}

double PID::applyDeadband(double value) {
    return 0.0;
}
