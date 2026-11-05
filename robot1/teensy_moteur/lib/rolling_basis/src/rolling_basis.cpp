/**
 * This is the implementation of the Rolling Basis class.
 * The Rolling Basis class is the core of the Motor teensy code.
 * It provides method to control the motors, the speed and the orientation.
 * It computes the odometry and correct the motors error with the PID class.
 */

#include <Arduino.h>
#include <rolling_basis.h>
#include <util/atomic.h>

double normalizeAngle(double theta) {
    // shift by +PI, take modulo 2*PI, remap to [0,2*PI)
    theta = fmodf(theta + PI, 2.0f * PI);
    if (theta < 0.0f) {
        theta += 2.0f * PI;
    }
    // shift back to [-PI, +PI)
    return theta - PI;
}

// Properties
/**
 * @brief Get current position (X, Y and THETA) of the robot
 *
 * @return Current position
 */
Point Rolling_Basis::get_current_position() {
    Point position;
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        position.x = this->X;
        position.y = this->Y;
        position.theta = this->THETA;
    }
    return position;
}

// Constructor
/**
 * @brief Constructor of the Rolling Basis class
 *
 * Initializes the parameters of the Rolling Basis
 */
Rolling_Basis::Rolling_Basis(unsigned short encoder_resolution,
                             double center_distance,
                             double wheel_diameter,
                             const PID& linear_distance_pid,
                             const PID& angular_distance_pid,
                             const PID& left_speed_pid,
                             const PID& right_speed_pid)
    : encoder_resolution(encoder_resolution),
      center_distance(center_distance),
      wheel_diameter(wheel_diameter),
      linear_distance_pid(linear_distance_pid),
      angular_distance_pid(angular_distance_pid),
      left_speed_pid(left_speed_pid),
      right_speed_pid(right_speed_pid) {}

// Methods
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
void Rolling_Basis::define_right_motor(byte enca,
                                       byte encb,
                                       byte pwm,
                                       byte dir,
                                       int pwm_max,
                                       double u_max,
                                       double ts) {
    this->right_motor = new Motor(
        dir, pwm, enca, encb, this->wheel_unit_tick_cm(), pwm_max, u_max, ts);
}

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
void Rolling_Basis::define_left_motor(byte enca,
                                      byte encb,
                                      byte pwm,
                                      byte dir,
                                      int pwm_max,
                                      double u_max,
                                      double ts) {
    this->left_motor = new Motor(
        dir, pwm, enca, encb, this->wheel_unit_tick_cm(), pwm_max, u_max, ts);
}

/**
 * @brief Initialize both motors
 */
void Rolling_Basis::init_motors() {
    this->right_motor->init();
    this->left_motor->init();
}

/**
 * @brief Initialize Rolling Basis state with starting position
 */
void Rolling_Basis::init_rolling_basis(double x, double y, double theta) {
    this->X = x;
    this->Y = y;
    this->THETA = theta;
}

// Odometrie function
/**
 * @brief Calcule le déplacement du robot sur la dernière période
 *
 * Met à jour les deux roues, puis en déduit la distance et la rotation du
 * robot. Ces valeurs sont ajoutées à delta_mes et psi_mes, qui servent aux
 * correcteurs et ne sont jamais recalés, puis à la pose X, Y, THETA.
 */
void Rolling_Basis::odometrie_handle() {
    /* Update motors positions by calling odometer_handle */
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        this->right_motor->handle_odometrie();
        this->left_motor->handle_odometrie();
    }

    /* Determine the delta of distance and rotation of the robot */
    double delta_distance =
        (this->left_motor->distance + this->right_motor->distance) / 2.0f;
    double delta_theta =
        (this->right_motor->distance - this->left_motor->distance) /
        this->center_distance;

    this->delta_mes += delta_distance;
    this->psi_mes += delta_theta;

    // Determine the new cartesian position of the robot
    this->X += cosf(this->THETA + (delta_theta / 2.0f)) * delta_distance;
    this->Y += sinf(this->THETA + (delta_theta / 2.0f)) * delta_distance;
    this->THETA = normalizeAngle(this->THETA + delta_theta);
}

/**
 * @brief Calcule et applique la commande des moteurs
 *
 * Appelée par le timer à chaque période, après odometrie_handle().
 * Hors POSITION, les moteurs sont coupés quand test_periods_left arrive à 0.
 * Selon le mode :
 * - OPEN_LOOP : applique directement u_left_target et u_right_target.
 * - SPEED : chaque PI calcule la tension de sa roue.
 * - POSITION : pas encore implémenté, les moteurs restent à 0 V.
 *
 * @param target_position Position cible du robot
 * @param com Objet de communication avec la Raspberry
 */
void Rolling_Basis::handle(Point target_position, Com* com) {
    // fin du test : on coupe les moteurs, même sans message de la Raspberry
    if (this->mode != Mode::POSITION) {
        if (this->test_periods_left == 0) {
            this->set_open_loop(0.0, 0.0);
        } else {
            this->test_periods_left--;
        }
    }

    // le mode décide quels étages de l'asservissement tournent
    switch (this->mode) {
        // aucun correcteur : les tensions vont directement aux moteurs
        case Mode::OPEN_LOOP:
            // consignes écrites par set_open_loop(), converties en PWM + DIR
            this->left_motor->set_voltage(this->u_left_target, this->vbat);
            this->right_motor->set_voltage(this->u_right_target, this->vbat);
            break;

        // chaque roue a son PI, qui transforme l'erreur de vitesse en tension
        case Mode::SPEED: {
            // erreur = vitesse cible - vitesse mesurée, en cm/s
            double u_left = this->left_speed_pid.compute(
                this->v_left_target - this->left_motor->speed);
            double u_right = this->right_speed_pid.compute(
                this->v_right_target - this->right_motor->speed);

            // set_voltage() convertit ces tensions en PWM + DIR
            this->left_motor->set_voltage(u_left, this->vbat);
            this->right_motor->set_voltage(u_right, this->vbat);
            break;
        }

        // cascade complète pas encore implémentée
        case Mode::POSITION:
            // 0 V explicite, sinon les moteurs gardent leur dernière PWM
            this->left_motor->set_voltage(0.0, this->vbat);
            this->right_motor->set_voltage(0.0, this->vbat);
            break;
    }
}

/**
 * @brief Passe en mode OPEN_LOOP avec une tension par moteur
 *
 * Le bloc atomique empêche le timer de s'exécuter pendant l'écriture : il
 * ne peut pas lire une consigne à moitié écrite, ni une seule des deux.
 * test_periods_left doit être réglé avant, sinon handle() coupe les moteurs.
 *
 * @param u_left Tension du moteur gauche, en V
 * @param u_right Tension du moteur droit, en V
 */
void Rolling_Basis::set_open_loop(double u_left, double u_right) {
    // le timer attend la fin du bloc : il voit les trois valeurs d'un coup
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        // tensions que handle() appliquera à la prochaine période
        this->u_left_target = u_left;
        this->u_right_target = u_right;
        // handle() utilise ces tensions uniquement dans ce mode
        this->mode = Mode::OPEN_LOOP;
    }
}

/**
 * @brief Passe en mode SPEED avec une vitesse par roue
 *
 * Les intégrales sont effacées seulement en entrant dans le mode SPEED.
 * Changer de vitesse quand on y est déjà ne les efface pas.
 * test_periods_left doit être réglé avant, sinon handle() coupe les moteurs.
 *
 * @param v_left Vitesse de la roue gauche, en cm/s
 * @param v_right Vitesse de la roue droite, en cm/s
 */
void Rolling_Basis::set_speed_targets(double v_left, double v_right) {
    // le timer attend la fin du bloc : il voit toutes les valeurs d'un coup
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        // une ancienne intégrale provoquerait un à-coup au démarrage
        if (this->mode != Mode::SPEED) {
            this->left_speed_pid.reset();
            this->right_speed_pid.reset();
        }
        // vitesses que handle() suivra à partir de la prochaine période
        this->v_left_target = v_left;
        this->v_right_target = v_right;
        // handle() utilise ces vitesses uniquement dans ce mode
        this->mode = Mode::SPEED;
    }
}