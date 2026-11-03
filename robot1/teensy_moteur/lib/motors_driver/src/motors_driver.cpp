/**
 * This is the implementation of the Motor class.
 * The Motor class control a Mmotor power and direction and handle odometry
 * computation.
 */

#include <Arduino.h>
#include <motors_driver.h>

/**
 * @brief Constructor of the Motor class
 * Define the pins of the motor, the related encoder pins and the properties of
 * the wheel attached to the motor
 */
Motor::Motor(byte pin_forward,
             byte pin_backward,
             byte pin_pwm,
             byte pin_enca,
             byte pin_encb,
             double wheel_unit_tick_cm,
             byte max_pwm,
             double ts) {
    this->pin_forward = pin_forward;
    this->pin_backward = pin_backward;

    this->pin_pwm = pin_pwm;    // PWM pin only !
    this->pin_enca = pin_enca;  // AttachInterrupt pin only !
    this->pin_encb = pin_encb;  // AttachInterrupt pin only !

    this->max_pwm = max_pwm;
    this->ts = ts;

    this->wheel_unit_tick_cm = wheel_unit_tick_cm;

    this->encoder = new Encoder(pin_enca, pin_encb);
}

/**
 * @brief Initialize the mode of the pins define for the motor
 */
void Motor::init() {
    pinMode(this->pin_forward, OUTPUT);
    pinMode(this->pin_backward, OUTPUT);
    pinMode(this->pin_pwm, OUTPUT);
    // la lib Encoder s'occupe de l'initialisation des pins des encodeurs
}

/**
 * @brief Set motor PWM and direction
 *
 * @param pwmVal Power value of the motor
 */
void Motor::set_motor(int pwmVal) {
    int16_t dir = pwmVal > 0 ? 1 : -1;
    pwmVal = constrain(abs(pwmVal), 0, this->max_pwm);
    analogWrite(this->pin_pwm, pwmVal);
    if (dir == 1) {
        digitalWrite(this->pin_forward, HIGH);
        digitalWrite(this->pin_backward, LOW);
    } else if (dir == -1) {
        digitalWrite(this->pin_forward, LOW);
        digitalWrite(this->pin_backward, HIGH);
    } else {
        digitalWrite(this->pin_forward, LOW);
        digitalWrite(this->pin_backward, LOW);
    }
}

/**
 * @brief Compute odometry.
 * Compute distance travelled by the encoders wheel and the speed of the
 * encoders wheel.
 */
void Motor::handle_odometrie() {
    // Update Ticks
    long ticks = this->encoder->read();
    long delta_ticks = ticks - this->last_ticks;
    this->last_ticks = ticks;

    // Compute new distance travelled
    this->distance = delta_ticks * this->wheel_unit_tick_cm;
    this->speed = this->distance / this->ts;  // en cm/s
}
