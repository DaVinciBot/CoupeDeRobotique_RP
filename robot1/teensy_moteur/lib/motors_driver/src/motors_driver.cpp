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
Motor::Motor(byte pin_dir,
             byte pin_pwm,
             byte pin_enca,
             byte pin_encb,
             double wheel_unit_tick_cm,
             int pwm_max,
             double u_max,
             double ts) {
    this->pin_dir = pin_dir;  // PIN de direction

    this->pin_pwm = pin_pwm;    // PWM pin only !
    this->pin_enca = pin_enca;  // AttachInterrupt pin only !
    this->pin_encb = pin_encb;  // AttachInterrupt pin only !

    this->pwm_max = pwm_max;
    this->ts = ts;

    this->u_max = u_max;

    this->wheel_unit_tick_cm = wheel_unit_tick_cm;

    this->encoder = new Encoder(pin_enca, pin_encb);
}

/**
 * @brief Initialize the mode of the pins define for the motor
 */
void Motor::init() {
    pinMode(this->pin_dir, OUTPUT);
    pinMode(this->pin_pwm, OUTPUT);
    // la lib Encoder s'occupe de l'initialisation des pins des encodeurs
}

/**
 * @brief Applique une tension au moteur
 *
 * Borne u à +/- u_max, puis calcule le rapport cyclique alpha = u / vbat.
 * Diviser par vbat garde la même tension moteur quand la batterie baisse.
 * Le signe d'alpha donne le sens (DIR) et sa valeur absolue donne la PWM.
 * Si vbat n'est pas valide, le moteur est coupé.
 *
 * @param u Tension à appliquer, en V (le signe donne le sens)
 * @param vbat Tension de la batterie, en V
 */
void Motor::set_voltage(double u, double vbat) {
    // on borne u
    if (u > this->u_max) {
        u = this->u_max;
    }
    if (u < -this->u_max) {
        u = -this->u_max;
    }

    // si vbat n'est pas valide, alpha reste à 0 et le moteur s'arrête
    double alpha = 0.0;
    if (vbat > 0.05) {
        alpha = u / vbat;
    }

    // borner alpha entre -1 et 1 pour ne pas depasser la tension de la batterie
    if (alpha > 1.0) {
        alpha = 1.0;
    }
    if (alpha < -1.0) {
        alpha = -1.0;
    }
    this->voltage = alpha * vbat;

    // on choisit le sens avec le signe d'alpha
    digitalWrite(this->pin_dir, alpha >= 0);

    // envoie du pwm
    analogWrite(this->pin_pwm, fabs(alpha) * this->pwm_max);
}

/**
 * @brief Met à jour la distance et la vitesse de la roue
 *
 * Lit le compteur de l'encodeur et le compare à la lecture précédente.
 * Les tics parcourus sont convertis en cm, puis divisés par la période ts
 * pour obtenir la vitesse en cm/s.
 * A appeler une seule fois par période.
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
