#include <motors_driver.h>

Motor::Motor(byte pin_dir,
             byte pin_pwm,
             byte pin_enca,
             byte pin_encb,
             int pwm_max,
             double u_max)
    : pin_dir(pin_dir),
      pin_pwm(pin_pwm),
      pwm_max(pwm_max),
      u_max(u_max),
      encoder(pin_enca, pin_encb) {}

void Motor::init() {
    pinMode(this->pin_dir, OUTPUT);
    pinMode(this->pin_pwm, OUTPUT);
    // the Encoder library sets the encoder pins itself
    this->set_voltage(0.0, 0.0);
}

void Motor::set_voltage(double u, double vbat) {
    u = constrain(u, -this->u_max, this->u_max);

    // if vbat is not valid, alpha stays at 0 and the motor stops
    double alpha = 0.0;
    if (vbat > 0.05) {
        alpha = constrain(u / vbat, -1.0, 1.0);
    }

    digitalWrite(this->pin_dir, alpha >= 0.0);
    analogWrite(this->pin_pwm, (int)(fabs(alpha) * this->pwm_max));
}

int32_t Motor::ticks() {
    return this->encoder.read();
}
