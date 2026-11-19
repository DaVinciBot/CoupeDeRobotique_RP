/**
 * Hardware side of one wheel: the motor driver (PWM + DIR) and the encoder
 * of the encoder wheel. The control itself is in motion_control.
 */

#ifndef MOTORS_DRIVER_H
#define MOTORS_DRIVER_H

#include <Arduino.h>
#include <Encoder.h>

class Motor {
   private:
    byte pin_dir;
    byte pin_pwm;  // PWM pin only
    int pwm_max;   // PWM max value (depends on the PWM resolution)
    double u_max;  // motor voltage limit, V
    Encoder encoder;

   public:
    /**
     * @param pin_enca, pin_encb Encoder pins (interrupt pins)
     */
    Motor(byte pin_dir,
          byte pin_pwm,
          byte pin_enca,
          byte pin_encb,
          int pwm_max,
          double u_max);

    /**
     * @brief Sets the pins, motor stopped
     */
    void init();

    /**
     * @brief Applies a voltage to the motor
     *
     * Limits u to +/- u_max, then sets the duty cycle alpha = u / vbat:
     * dividing by vbat keeps the same motor voltage when the battery gets
     * low (D3). The sign of alpha gives DIR. If vbat is not valid, the motor
     * is stopped.
     *
     * @param u Voltage, V (the sign gives the direction)
     * @param vbat Battery voltage, V
     */
    void set_voltage(double u, double vbat);

    /**
     * @brief Encoder count since start-up
     */
    int32_t ticks();
};

#endif  // MOTORS_DRIVER_H
