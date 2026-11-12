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
                             const PID& right_speed_pid,
                             const Trapezoid& delta_profile,
                             const Trapezoid& psi_profile,
                             double ts,
                             double position_tolerance,
                             double angle_tolerance,
                             double block_voltage,
                             double block_speed,
                             unsigned long block_periods,
                             double push_voltage)
    : encoder_resolution(encoder_resolution),
      center_distance(center_distance),
      wheel_diameter(wheel_diameter),
      linear_distance_pid(linear_distance_pid),
      angular_distance_pid(angular_distance_pid),
      left_speed_pid(left_speed_pid),
      right_speed_pid(right_speed_pid),
      delta_profile(delta_profile),
      psi_profile(psi_profile),
      ts(ts),
      position_tolerance(position_tolerance),
      angle_tolerance(angle_tolerance),
      block_voltage(block_voltage),
      block_speed(block_speed),
      block_periods(block_periods),
      push_voltage(push_voltage) {}

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
 * En OPEN_LOOP et SPEED, les moteurs sont coupés quand test_periods_left
 * arrive à 0. Selon le mode :
 * - OPEN_LOOP : applique directement u_left_target et u_right_target.
 * - SPEED : chaque PI calcule la tension de sa roue.
 * - POSITION : suit les trapèzes avec la cascade complète.
 * - PUSH : vitesse imposée, tension bornée, jusqu'au blocage.
 */
void Rolling_Basis::handle() {
    // fin du test : on coupe les moteurs, même sans message de la Raspberry
    if (this->mode == Mode::OPEN_LOOP || this->mode == Mode::SPEED) {
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

        // seules les boucles de vitesse tournent
        case Mode::SPEED:
            this->apply_speed_targets();
            break;

        // cascade complète : trapèze, position, répartition puis vitesse
        case Mode::POSITION: {
            this->update_move();

            this->delta_profile.step(this->ts);
            this->psi_profile.step(this->ts);

            // anticipation (vitesse prévue) + correction de l'erreur restante
            double v_c = this->delta_profile.speed +
                         this->linear_distance_pid.compute(
                             this->delta_profile.position - this->delta_mes);
            double w_c = this->psi_profile.speed +
                         this->angular_distance_pid.compute(
                             this->psi_profile.position - this->psi_mes);

            // v_c fait avancer les deux roues, w_c les sépare pour tourner
            this->v_left_target = v_c - this->center_distance / 2.0 * w_c;
            this->v_right_target = v_c + this->center_distance / 2.0 * w_c;

            this->apply_speed_targets();
            this->check_blocked();
            break;
        }

        // vitesse imposée jusqu'à la bordure, abandon après max_distance
        case Mode::PUSH:
            // rien touché : la Raspberry verra STOPPED au lieu de BLOCKED
            if (fabs(this->delta_mes - this->push_start) >=
                this->push_max_distance) {
                this->set_open_loop(0.0, 0.0);
                break;
            }
            this->apply_speed_targets(this->push_voltage);
            this->check_blocked();
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
        // un essai remplace le déplacement en cours
        this->move_step = MoveStep::IDLE;
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
        // un essai remplace le déplacement en cours
        this->move_step = MoveStep::IDLE;
    }
}

/**
 * @brief Applique les vitesses de consigne aux deux roues
 *
 * Chaque PI transforme l'erreur de vitesse de sa roue en tension. Cette étape
 * est commune aux modes SPEED, POSITION et PUSH.
 *
 * @param u_limit Tension max appliquée, en V (bornée ensuite à u_max)
 */
void Rolling_Basis::apply_speed_targets(double u_limit) {
    // erreur = vitesse cible - vitesse mesurée, en cm/s
    double u_left = this->left_speed_pid.compute(this->v_left_target -
                                                 this->left_motor->speed);
    double u_right = this->right_speed_pid.compute(this->v_right_target -
                                                   this->right_motor->speed);

    u_left = fmax(fmin(u_left, u_limit), -u_limit);
    u_right = fmax(fmin(u_right, u_limit), -u_limit);

    // set_voltage() convertit ces tensions en PWM + DIR
    this->left_motor->set_voltage(u_left, this->vbat);
    this->right_motor->set_voltage(u_right, this->vbat);
}

/**
 * @brief Lance un déplacement vers une cible de la table
 *
 * Le mouvement est découpé en trois étapes : se tourner vers la cible, avancer,
 * puis prendre l'angle final. Les consignes repartent de la mesure actuelle,
 * pour que le robot ne saute pas vers une ancienne consigne.
 * A envoyer quand le mouvement précédent est fini : une nouvelle cible remet
 * tout de suite les vitesses prévues à zéro.
 *
 * @param target Cible : x et y en cm, theta en rad
 */
void Rolling_Basis::set_target(Point target) {
    // le timer attend la fin du bloc : il ne voit jamais un mouvement à moitié
    // préparé
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        // une ancienne intégrale provoquerait un à-coup au démarrage
        if (this->mode != Mode::POSITION) {
            this->left_speed_pid.reset();
            this->right_speed_pid.reset();
            this->linear_distance_pid.reset();
            this->angular_distance_pid.reset();
        }

        this->target = target;
        this->test_periods_left = 0;
        this->blocked = false;
        this->blocked_count = 0;

        // distance et angle tiennent la position actuelle tant qu'on ne les
        // fait pas bouger
        this->delta_profile.start(this->delta_mes, 0.0);
        this->psi_profile.start(this->psi_mes, 0.0);
        this->start_rotate_to_target();

        this->mode = Mode::POSITION;
    }
}

/**
 * @brief Recule ou avance tout droit jusqu'à toucher une bordure
 *
 * Les deux roues suivent la même vitesse, avec une tension bornée à
 * push_voltage pour limiter la force contre la bordure. Quand une seule roue
 * est bloquée, l'autre continue et le robot pivote jusqu'à se plaquer.
 *
 * @param speed Vitesse des roues, en cm/s, négative pour reculer
 * @param max_distance Distance avant abandon, en cm
 */
void Rolling_Basis::push_until_blocked(double speed, double max_distance) {
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        // une ancienne intégrale provoquerait un à-coup au démarrage
        if (this->mode != Mode::PUSH) {
            this->left_speed_pid.reset();
            this->right_speed_pid.reset();
        }

        this->v_left_target = speed;
        this->v_right_target = speed;
        this->push_start = this->delta_mes;
        this->push_max_distance = fabs(max_distance);
        this->test_periods_left = 0;
        this->blocked = false;
        this->blocked_count = 0;
        this->move_step = MoveStep::IDLE;

        this->mode = Mode::PUSH;
    }
}

/**
 * @brief Impose la position absolue du robot (recalage)
 *
 * Seule la pose X, Y, THETA change : delta_mes et psi_mes, suivis par les
 * correcteurs, ne bougent pas, donc le robot ne saute pas.
 *
 * @param pose Nouvelle pose : x et y en cm, theta en rad
 * @return true si la pose est appliquée, false si le robot bouge
 */
bool Rolling_Basis::reset_pose(Point pose) {
    bool applied = false;
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        // la cible du mouvement en cours a été calculée avec l'ancienne pose
        if (this->get_status() != Status::MOVING) {
            this->X = pose.x;
            this->Y = pose.y;
            this->THETA = normalizeAngle(pose.theta);
            applied = true;
        }
    }
    return applied;
}

/**
 * @brief Démarre la rotation vers la cible
 *
 * Si le robot est déjà sur la cible, il passe directement à l'angle final.
 */
void Rolling_Basis::start_rotate_to_target() {
    double dx = this->target.x - this->X;
    double dy = this->target.y - this->Y;

    if (hypot(dx, dy) < this->position_tolerance) {
        this->start_rotate_final();
        return;
    }

    // la pose dit où aller, psi_mes sert de référence pour y aller sans saut
    double angle = normalizeAngle(atan2(dy, dx) - this->THETA);
    this->psi_profile.start(this->psi_mes, angle);
    this->move_step = MoveStep::ROTATE_TO_TARGET;
}

/**
 * @brief Démarre la ligne droite vers la cible
 *
 * La distance est recalculée avec la pose atteinte après la rotation.
 */
void Rolling_Basis::start_forward() {
    double distance = hypot(this->target.x - this->X, this->target.y - this->Y);

    this->delta_profile.start(this->delta_mes, distance);
    this->move_step = MoveStep::FORWARD;
}

/**
 * @brief Démarre la rotation vers l'angle final de la cible
 */
void Rolling_Basis::start_rotate_final() {
    double angle = normalizeAngle(this->target.theta - this->THETA);

    this->psi_profile.start(this->psi_mes, angle);
    this->move_step = MoveStep::ROTATE_FINAL;
}

/**
 * @brief Passe à l'étape suivante quand l'étape en cours est finie
 *
 * Une étape est finie quand le trapèze est terminé et que la mesure est
 * arrivée à la consigne, à la tolérance près.
 */
void Rolling_Basis::update_move() {
    bool rotation_done = this->psi_profile.finished() &&
                         fabs(this->psi_profile.position - this->psi_mes) <
                             this->angle_tolerance;
    bool forward_done = this->delta_profile.finished() &&
                        fabs(this->delta_profile.position - this->delta_mes) <
                            this->position_tolerance;

    switch (this->move_step) {
        case MoveStep::ROTATE_TO_TARGET:
            if (rotation_done) {
                this->start_forward();
            }
            break;

        case MoveStep::FORWARD:
            if (forward_done) {
                this->start_rotate_final();
            }
            break;

        case MoveStep::ROTATE_FINAL:
            if (rotation_done) {
                this->move_step = MoveStep::IDLE;
            }
            break;

        // le robot reste asservi sur sa dernière consigne
        case MoveStep::IDLE:
            break;
    }
}

/**
 * @brief Coupe les moteurs si une roue force sans avancer
 *
 * Une roue est bloquée si sa tension dépasse block_voltage alors que sa vitesse
 * reste sous block_speed. Après block_periods périodes de suite, le robot
 * s'arrête et blocked passe à true jusqu'à la prochaine cible.
 * En PUSH, il faut les deux roues, et la tension est comparée à push_voltage.
 */
void Rolling_Basis::check_blocked() {
    bool pushing = this->mode == Mode::PUSH;
    // en poussée, une roue qui force reste à la borne push_voltage
    double voltage_threshold =
        pushing ? 0.9 * this->push_voltage : this->block_voltage;

    bool left_blocked =
        fabs(this->left_motor->voltage) > voltage_threshold &&
        fabs(this->left_motor->speed) < this->block_speed;
    bool right_blocked =
        fabs(this->right_motor->voltage) > voltage_threshold &&
        fabs(this->right_motor->speed) < this->block_speed;

    // en poussée, une seule roue bloquée veut dire que le robot pivote pour se
    // plaquer contre la bordure : on continue
    bool is_blocked = pushing ? left_blocked && right_blocked
                              : left_blocked || right_blocked;

    // il faut un blocage continu : un démarrage difficile ne compte pas
    if (!is_blocked) {
        this->blocked_count = 0;
        return;
    }

    this->blocked_count++;
    if (this->blocked_count < this->block_periods) {
        return;
    }

    // sans ça, un moteur bloqué consommerait environ 9 A en continu
    this->blocked = true;
    this->test_periods_left = 0;
    this->set_open_loop(0.0, 0.0);
}

/**
 * @brief Donne l'état du robot, envoyé à la Raspberry
 *
 * @return Bloqué, en mouvement ou à l'arrêt
 */
Rolling_Basis::Status Rolling_Basis::get_status() {
    if (this->blocked) {
        return Status::BLOCKED;
    }
    if (this->mode == Mode::PUSH || this->move_step != MoveStep::IDLE) {
        return Status::MOVING;
    }
    return Status::STOPPED;
}
