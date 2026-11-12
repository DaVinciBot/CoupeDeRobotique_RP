/**
 * This is the Rolling Basis class header.
 * The Rolling Basis class is the core of the Motor teensy code.
 * It provides method to control the motors, the speed and the orientation.
 * It computes the odometry and correct the motors error with the PID class.
 */

#include <Arduino.h>
#include <motors_driver.h>
#include <pid.h>
#include <trapezoid.h>
#include "structures.h"

#include <com.h>  // Communication object to manage the communication between the teensy and the Raspberry Pi

class Rolling_Basis {
   public:
    // PID controllers
    PID linear_distance_pid;   // sortie : vitesse, en cm/s
    PID angular_distance_pid;  // sortie : vitesse, en rad/s
    PID left_speed_pid;        // sortie : tension, en V
    PID right_speed_pid;       // sortie : tension, en V

    // Générateurs de consigne
    Trapezoid delta_profile;  // distance, en cm
    Trapezoid psi_profile;    // angle, en rad

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

    // OPEN_LOOP : tension imposée, SPEED : vitesse imposée, POSITION : cascade,
    // PUSH : vitesse imposée jusqu'au blocage contre une bordure
    enum class Mode { OPEN_LOOP, SPEED, POSITION, PUSH };
    volatile Mode mode = Mode::OPEN_LOOP;

    // tension demandée au moteur gauche, en V
    volatile double u_left_target = 0.0;
    // tension demandée au moteur droit, en V
    volatile double u_right_target = 0.0;
    // vitesse demandée à la roue gauche, en cm/s
    volatile double v_left_target = 0.0;
    // vitesse demandée à la roue droite, en cm/s
    volatile double v_right_target = 0.0;
    // périodes restantes avant de couper les moteurs en fin de test
    volatile unsigned long test_periods_left = 0;

    // étapes d'un déplacement vers une cible, IDLE quand il n'y en a pas
    enum class MoveStep { IDLE, ROTATE_TO_TARGET, FORWARD, ROTATE_FINAL };
    volatile MoveStep move_step = MoveStep::IDLE;
    Point target;  // cible du mouvement en cours

    // état envoyé à la Raspberry, mêmes valeurs que côté Python
    enum class Status : byte { STOPPED = 0, MOVING = 1, BLOCKED = 2 };

    double ts;                  // période de la boucle, en s
    double position_tolerance;  // écart accepté à l'arrivée, en cm
    double angle_tolerance;     // écart accepté à l'arrivée, en rad

    // Détection de blocage
    double block_voltage;         // tension au-dessus de laquelle on force
    double block_speed;           // vitesse sous laquelle la roue est arrêtée
    unsigned long block_periods;  // périodes avant de couper les moteurs
    unsigned long blocked_count = 0;  // périodes de blocage à la suite
    volatile bool blocked = false;    // reste vrai jusqu'à la prochaine cible

    // Poussée contre une bordure
    double push_voltage;              // tension max des roues, en V
    double push_start = 0.0;          // delta_mes au début de la poussée
    double push_max_distance = 0.0;   // distance avant abandon, en cm

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
                  double push_voltage);

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
     * Hors POSITION, les moteurs sont coupés quand test_periods_left arrive à
     * 0. Selon le mode :
     * - OPEN_LOOP : applique directement u_left_target et u_right_target.
     * - SPEED : chaque PI calcule la tension de sa roue.
     * - POSITION : suit les trapèzes avec la cascade complète.
     */
    void handle();

    /**
     * @brief Passe en mode OPEN_LOOP avec une tension par moteur
     *
     * Le bloc atomique empêche le timer de s'exécuter pendant l'écriture : il
     * ne peut pas lire une consigne à moitié écrite, ni une seule des deux.
     * test_periods_left doit être réglé avant, sinon handle() coupe les
     * moteurs.
     *
     * @param u_left Tension du moteur gauche, en V
     * @param u_right Tension du moteur droit, en V
     */
    void set_open_loop(double u_left, double u_right);

    /**
     * @brief Passe en mode SPEED avec une vitesse par roue
     *
     * Les intégrales sont effacées seulement en entrant dans le mode SPEED.
     * Changer de vitesse quand on y est déjà ne les efface pas.
     * test_periods_left doit être réglé avant, sinon handle() coupe les
     * moteurs.
     *
     * @param v_left Vitesse de la roue gauche, en cm/s
     * @param v_right Vitesse de la roue droite, en cm/s
     */
    void set_speed_targets(double v_left, double v_right);

    /**
     * @brief Lance un déplacement vers une cible de la table
     *
     * Le mouvement est découpé en trois étapes : se tourner vers la cible,
     * avancer, puis prendre l'angle final. Les consignes repartent de la mesure
     * actuelle, pour que le robot ne saute pas vers une ancienne consigne. A
     * envoyer quand le mouvement précédent est fini : une nouvelle cible remet
     * tout de suite les vitesses prévues à zéro.
     *
     * @param target Cible : x et y en cm, theta en rad
     */
    void set_target(Point target);

    /**
     * @brief Recule ou avance tout droit jusqu'à toucher une bordure
     *
     * Les deux roues suivent la même vitesse, avec une tension bornée à
     * push_voltage pour limiter la force contre la bordure. Quand une seule
     * roue est bloquée, l'autre continue et le robot pivote jusqu'à se plaquer.
     * Le statut passe à BLOCKED quand les deux roues sont bloquées, ou à
     * STOPPED si le robot a parcouru max_distance sans rien toucher.
     *
     * @param speed Vitesse des roues, en cm/s, négative pour reculer
     * @param max_distance Distance avant abandon, en cm
     */
    void push_until_blocked(double speed, double max_distance);

    /**
     * @brief Impose la position absolue du robot (recalage)
     *
     * Seule la pose X, Y, THETA change : delta_mes et psi_mes, suivis par les
     * correcteurs, ne bougent pas, donc le robot ne saute pas. Refusé pendant
     * un mouvement, dont la cible a été calculée avec l'ancienne pose.
     *
     * @param pose Nouvelle pose : x et y en cm, theta en rad
     * @return true si la pose est appliquée, false si le robot bouge
     */
    bool reset_pose(Point pose);

    /**
     * @brief Passe à l'étape suivante quand l'étape en cours est finie
     *
     * Une étape est finie quand le trapèze est terminé et que la mesure est
     * arrivée à la consigne, à la tolérance près.
     */
    void update_move();

    /**
     * @brief Démarre la rotation vers la cible
     *
     * Si le robot est déjà sur la cible, il passe directement à l'angle final.
     */
    void start_rotate_to_target();

    /**
     * @brief Démarre la ligne droite vers la cible
     *
     * La distance est recalculée avec la pose atteinte après la rotation.
     */
    void start_forward();

    /**
     * @brief Démarre la rotation vers l'angle final de la cible
     */
    void start_rotate_final();

    /**
     * @brief Applique les vitesses de consigne aux deux roues
     *
     * Chaque PI transforme l'erreur de vitesse de sa roue en tension. Cette
     * étape est commune aux modes SPEED, POSITION et PUSH.
     *
     * @param u_limit Tension max appliquée, en V (bornée ensuite à u_max)
     */
    void apply_speed_targets(double u_limit = INFINITY);

    /**
     * @brief Coupe les moteurs si une roue force sans avancer
     *
     * Une roue est bloquée si sa tension dépasse block_voltage alors que sa
     * vitesse reste sous block_speed. Après block_periods périodes de suite, le
     * robot s'arrête et blocked passe à true jusqu'à la prochaine cible.
     * En PUSH, il faut les deux roues, et la tension est comparée à
     * push_voltage.
     */
    void check_blocked();

    /**
     * @brief Donne l'état du robot, envoyé à la Raspberry
     *
     * @return Bloqué, en mouvement ou à l'arrêt
     */
    Status get_status();

    void pi_mod_signed(double theta);

    // Motors action function
    // void keep_position(long current_right_ticks, long current_left_ticks);
    // void shutdown_motor();
};
