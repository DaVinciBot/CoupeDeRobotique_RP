/**
 * This is the Motor class header.
 * The Motor class control a Mmotor power and direction and handle odometry
 * computation.
 */

#include <Arduino.h>
#include <Encoder.h>

// Motor class
class Motor {
   private:
    // Pins Motor
    byte pin_dir;   // PIN de direction
    byte pin_pwm;   // PWM pin only !
    byte pin_enca;  // AttachInterrupt pin only !
    byte pin_encb;  // AttachInterrupt pin only !

    int pwm_max;  // PWM max value (depends on PWM resolution)

    // Ticks distance
    double wheel_unit_tick_cm;

    double ts;  // période de la boucle, en s

    double u_max;  // tension maximale du moteur, en V
   public:
    Encoder* encoder;  // Encoder object to handle the encoder of the motor

    // Motor description (it is the last data calculated by the motor odometer
    // handle method)
    double distance = 0.0;  // Distance in cm
    long last_ticks = 0L;   // Ticks distance used to compute distance and speed
                            // (updated at the last odometer handle call)
    double speed = 0.0;     // en cm/s

    double voltage = 0.0;  // dernière tension appliquée, en V

    // Constructor
    /**
     * @brief Constructor of the Motor class
     * Define the pins of the motor, the related encoder pins and the properties
     * of the wheel attached to the motor
     */
    Motor(byte pin_dir,
          byte pin_pwm,
          byte pin_enca,
          byte pin_encb,
          double wheel_unit_tick_cm,
          int pwm_max,
          double u_max,
          double ts);
    ~Motor() = default;

    // Methods
    /**
     * @brief Initialize the mode of the pins define for the motor
     */
    void init();

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
    void set_voltage(double u, double vbat);

    /**
     * @brief Met à jour la distance et la vitesse de la roue
     *
     * Lit le compteur de l'encodeur et le compare à la lecture précédente.
     * Les tics parcourus sont convertis en cm, puis divisés par la période ts
     * pour obtenir la vitesse en cm/s.
     * A appeler une seule fois par période.
     */
    void handle_odometrie();
};
