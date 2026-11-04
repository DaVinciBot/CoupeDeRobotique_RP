/**
 * This is the Rolling Basis class header.
 * The Rolling Basis class is the core of the Motor teensy code.
 * It provides method to control the motors, the speed and the orientation.
 * It computes the odometry and correct the motors error with the PID class.
 */

#include <Arduino.h>
#include <motors_driver.h>
#include <pid.h>
#include "structures.h"

#include <com.h>  // Communication object to manage the communication between the teensy and the Raspberry Pi

class Rolling_Basis {
   public:
    // PID controllers
    PID linear_distance_pid;
    PID angular_distance_pid;

    // Rolling basis's params
    inline double radius() { return this->center_distance / 2.0; };
    inline double wheel_perimeter() { return this->wheel_diameter * PI; };
    inline double wheel_unit_tick_cm() {
        return this->wheel_perimeter() / this->encoder_resolution;
    };

    // Properties
    /**
     * @brief Get current position (X, Y and THETA) of the robot
     *
     * @return Current position
     */
    Point get_current_position();

    // Rolling basis's motors
    Motor* right_motor;
    Motor* left_motor;

    // Odometrie
    double X = 0.0f;
    double Y = 0.0f;
    double THETA = 0.0f;

    double delta_mes = 0.0;  // distance cumulée, en cm, jamais recalée
    double psi_mes = 0.0;    // angle cumulé, en rad, jamais recalé

    // Rolling basis params
    unsigned short encoder_resolution;
    double center_distance;
    double wheel_diameter;

    // V de la batterie
    double vbat = 0.0;  // en V

    // OPEN_LOOP : tension imposée, SPEED : vitesse imposée, POSITION : cascade
    enum class Mode { OPEN_LOOP, SPEED, POSITION };
    volatile Mode mode = Mode::OPEN_LOOP;

    // tension demandée au moteur gauche, en V
    volatile double u_left_target = 0.0;
    // tension demandée au moteur droit, en V
    volatile double u_right_target = 0.0;

    // Constructor
    /**
     * @brief constructor of the Rolling Basis class
     *
     * Initializes the parameters of the Rolling Basis
     */
    Rolling_Basis(unsigned short encoder_resolution,
                  double center_distance,
                  double wheel_diameter,
                  const PID& linear_distance_pid,
                  const PID& angular_distance_pid);

    /**
     * @brief Destructor of Rolling Basis class
     */
    ~Rolling_Basis() = default;

    // Inits function
    /**
     * @brief Crée le moteur droit avec ses broches et ses paramètres
     *
     * @param enca Broche A de l'encodeur
     * @param encb Broche B de l'encodeur
     * @param pwm Broche PWM du driver
     * @param dir Broche de sens du driver
     * @param pwm_max Valeur PWM maximale (dépend de la résolution)
     * @param u_max Tension maximale du moteur, en V
     * @param ts Période de la boucle, en s
     */
    void define_right_motor(byte enca,
                            byte encb,
                            byte pwm,
                            byte dir,
                            int pwm_max,
                            double u_max,
                            double ts);
    /**
     * @brief Crée le moteur gauche avec ses broches et ses paramètres
     *
     * @param enca Broche A de l'encodeur
     * @param encb Broche B de l'encodeur
     * @param pwm Broche PWM du driver
     * @param dir Broche de sens du driver
     * @param pwm_max Valeur PWM maximale (dépend de la résolution)
     * @param u_max Tension maximale du moteur, en V
     * @param ts Période de la boucle, en s
     */
    void define_left_motor(byte enca,
                           byte encb,
                           byte pwm,
                           byte dir,
                           int pwm_max,
                           double u_max,
                           double ts);
    /**
     * @brief Initialize both motors
     */
    void init_motors();
    /**
     * @brief Initialize Rolling Basis state with starting position
     */
    void init_rolling_basis(double x, double y, double theta);

    // Odometrie function
    /**
     * @brief Calcule le déplacement du robot sur la dernière période
     *
     * Met à jour les deux roues, puis en déduit la distance et la rotation du
     * robot. Ces valeurs sont ajoutées à delta_mes et psi_mes, qui servent aux
     * correcteurs et ne sont jamais recalés, puis à la pose X, Y, THETA.
     */
    void odometrie_handle();
    /**
     * @brief Calcule et applique la commande des moteurs
     *
     * Appelée par le timer à chaque période, après odometrie_handle().
     * Selon le mode :
     * - OPEN_LOOP : applique directement u_left_target et u_right_target.
     * - SPEED et POSITION : pas encore implémentés, les moteurs restent à 0 V.
     *
     * @param target_position Position cible du robot
     * @param com Objet de communication avec la Raspberry
     */
    void handle(Point target_position, Com* com);

    /**
     * @brief Passe en mode OPEN_LOOP avec une tension par moteur
     *
     * Le bloc atomique empêche le timer de s'exécuter pendant l'écriture : il
     * ne peut pas lire une consigne à moitié écrite, ni une seule des deux.
     *
     * @param u_left Tension du moteur gauche, en V
     * @param u_right Tension du moteur droit, en V
     */
    void set_open_loop(double u_left, double u_right);

    void pi_mod_signed(double theta);

    // Motors action function
    // void keep_position(long current_right_ticks, long current_left_ticks);
    // void shutdown_motor();
};
