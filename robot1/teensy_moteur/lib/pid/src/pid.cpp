/**
 * This is the implementation of the PID class.
 * The PID class computes the command of the servo-control from an error.
 */

#include "pid.h"
#include <Arduino.h>

PID::PID(double kp,
         double ki,
         double kd,
         double minOutput,
         double maxOutput,
         double ts)
    : _kp(kp),
      _ki(ki),
      _kd(kd),
      _minOutput(minOutput),
      _maxOutput(maxOutput),
      _integral(0.0),
      _ts(ts) {}

void PID::updateParameters(double kp, double ki, double kd) {
    this->setTunings(kp, ki, kd);
    // l'ancienne intégrale a été calculée avec les anciens gains
    this->reset();
}

void PID::setTunings(double kp, double ki, double kd) {
    this->_kp = kp;
    this->_ki = ki;
    this->_kd = kd;
}

void PID::setOutputLimits(double minOutput, double maxOutput) {
    if (minOutput >= maxOutput) {
        return;  // bornes invalides : on garde les anciennes
    }
    this->_minOutput = minOutput;
    this->_maxOutput = maxOutput;
}

void PID::reset() {
    this->_integral = 0.0;
}

double PID::compute(double error) {
    // correction immédiate + correction accumulée
    double output = this->_kp * error + this->_integral;

    // sortie saturée : on renvoie la borne sans intégrer, pour que l'intégrale
    // ne grossisse pas sans fin si une roue est bloquée
    if (output > this->_maxOutput) {
        return this->_maxOutput;
    }
    if (output < this->_minOutput) {
        return this->_minOutput;
    }

    // hors saturation : l'erreur s'accumule pour la période suivante
    this->_integral += this->_ki * error * this->_ts;
    return output;
}