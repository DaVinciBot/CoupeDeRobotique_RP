// Fait tourner le vrai code de la base roulante avec des moteurs simulés.
// Seul le matériel est remplacé (dossier fake). Lancer avec run.ps1.
//
// Usage : simulation.exe normal|blocage|recalage

#include <Arduino.h>
#include <config.h>
#include <rolling_basis.h>
#include <stdio.h>
#include <string.h>

// Moteurs simulés : valeurs d'exemple, à remplacer par les valeurs mesurées
const double K_LEFT = 5.0;     // vitesse finale par volt, en cm/s/V
const double K_RIGHT = 4.5;    // volontairement un peu plus faible à droite
const double TAU = 0.1;        // temps de réaction du moteur, en s
const double DEAD_ZONE = 1.0;  // tension perdue dans les frottements, en V

// Réglage des correcteurs (doc de Fadi, 7.1 et 7.2)
const double TAU_V = 0.05;  // temps de réaction voulu pour la vitesse, en s
const double K_POSITION = 0.5 / TAU_V;

// Mouvement demandé
const double TARGET_X = 50.0;      // en cm
const double TARGET_Y = 50.0;      // en cm
const double TARGET_THETA = 1.57;  // en rad
const double DURATION = 12.0;      // durée de la simulation, en s

// Avec l'option blocage, la roue gauche se bloque à cet instant
const double BLOCK_START = 4.0;  // en s

// Recalage contre les bordures du bas (y = 0) puis de gauche (x = 0).
// Géométrie d'exemple, à remplacer par les mesures de la méca
const double D_BACK = 12.0;      // centre des roues -> face arrière, en cm
const double HALF_WIDTH = 15.0;  // demi-largeur de la face arrière, en cm
const double PUSH_SPEED = -5.0;  // recul, en cm/s
const double PUSH_MAX_DISTANCE = 40.0;  // en cm
const double CLEARANCE = 8.0;  // dégagement après chaque recalage, en cm
const double RECALAGE_DURATION = 40.0;  // en s

// Pose réelle au départ, et pose que croit le robot (erreur volontaire)
const double TRUE_START_X = 30.0;  // en cm
const double TRUE_START_Y = 22.0;  // en cm
const double TRUE_START_THETA = PI / 2 + 0.05;  // en rad, environ 3° d'écart
const double BELIEVED_START_X = 27.0;
const double BELIEVED_START_Y = 25.0;
const double BELIEVED_START_THETA = PI / 2;

const int SUB_STEPS = 50;  // calculs du moteur par période de la boucle

struct Wheel {
    double k;
    byte pin_pwm;
    byte pin_dir;
    byte pin_enca;
    double speed = 0.0;     // en cm/s
    double distance = 0.0;  // en cm
};

// Pose réelle du robot sur la table, que le code de la Teensy ne voit pas
struct Pose {
    double x;      // en cm
    double y;      // en cm
    double theta;  // en rad
};

// Avance la pose réelle avec les distances parcourues par les roues
void update_true_pose(Pose& pose, double d_left, double d_right) {
    double d = (d_left + d_right) / 2.0;
    double d_theta = (d_right - d_left) / ENTRAXE;
    pose.x += cos(pose.theta + d_theta / 2.0) * d;
    pose.y += sin(pose.theta + d_theta / 2.0) * d;
    pose.theta += d_theta;
}

// Vrai si le coin arrière gauche (side = 1) ou droit (side = -1) touche la
// bordure du bas ou de gauche
bool rear_corner_on_wall(const Pose& pose, double side) {
    double x = pose.x - D_BACK * cos(pose.theta) -
               side * HALF_WIDTH * sin(pose.theta);
    double y = pose.y - D_BACK * sin(pose.theta) +
               side * HALF_WIDTH * cos(pose.theta);
    return x <= 0.0 || y <= 0.0;
}

double angle_error(double a, double b) {
    return atan2(sin(a - b), cos(a - b));
}

void print_pose_error(const char* label, Rolling_Basis& robot,
                      const Pose& pose) {
    printf("[recalage] %s : erreur x = %+.2f cm, y = %+.2f cm, theta = %+.2f deg\n",
           label, robot.X - pose.x, robot.Y - pose.y,
           angle_error(robot.THETA, pose.theta) * 180.0 / PI);
}

// Calcule une période du moteur à partir des broches écrites par le code
// wall : un coin arrière touche une bordure, la roue ne peut plus reculer
void update_wheel(Wheel& wheel, double tick_cm, bool blocked,
                  bool wall = false) {
    double u = fake_pwm[wheel.pin_pwm] * VBAT_DEFAULT / PWM_MAX;
    if (!fake_dir[wheel.pin_dir]) {
        u = -u;
    }

    // la zone morte retire une partie de la tension appliquée
    double useful = fmax(fabs(u) - DEAD_ZONE, 0.0);
    double u_effective = u >= 0.0 ? useful : -useful;

    // premier ordre de la doc de Fadi : tau * dv/dt = K * u - v
    double dt = TS / SUB_STEPS;
    for (int i = 0; i < SUB_STEPS; i++) {
        wheel.speed += dt * (wheel.k * u_effective - wheel.speed) / TAU;
        if (blocked || (wall && wheel.speed < 0.0)) {
            wheel.speed = 0.0;
        }
        wheel.distance += wheel.speed * dt;
    }

    // l'encodeur ne voit que des tics entiers, comme sur le robot
    fake_ticks[wheel.pin_enca] = floor(wheel.distance / tick_cm);
}

int main(int argc, char** argv) {
    const char* scenario = argc > 1 ? argv[1] : "normal";
    bool block_left = strcmp(scenario, "blocage") == 0;
    bool recalage = strcmp(scenario, "recalage") == 0;

    // gains du PI : Kp = tau / (K * tau_v) et Ki = Kp / tau
    double kp_left = TAU / (K_LEFT * TAU_V);
    double kp_right = TAU / (K_RIGHT * TAU_V);

    PID linear_pid(K_POSITION, 0, 0, -V_MAX, V_MAX, TS);
    PID angular_pid(K_POSITION, 0, 0, -W_MAX, W_MAX, TS);
    PID left_pid(kp_left, kp_left / TAU, 0, -U_MAX, U_MAX, TS);
    PID right_pid(kp_right, kp_right / TAU, 0, -U_MAX, U_MAX, TS);
    Trapezoid delta_profile(V_MAX, ACC_MAX);
    Trapezoid psi_profile(W_MAX, W_ACC_MAX);

    Rolling_Basis robot(ENCODER_RESOLUTION, ENTRAXE, WHEEL_DIAMETER, linear_pid,
                        angular_pid, left_pid, right_pid, delta_profile,
                        psi_profile, TS, POSITION_TOLERANCE, ANGLE_TOLERANCE,
                        BLOCK_VOLTAGE, BLOCK_SPEED, BLOCK_PERIODS,
                        PUSH_VOLTAGE);
    robot.define_right_motor(R_ENCA, R_ENCB, R_PWM, R_DIR, PWM_MAX, U_MAX, TS);
    robot.define_left_motor(L_ENCA, L_ENCB, L_PWM, L_DIR, PWM_MAX, U_MAX, TS);
    robot.init_motors();
    robot.vbat = VBAT_DEFAULT;

    Wheel left = {K_LEFT, L_PWM, L_DIR, L_ENCA};
    Wheel right = {K_RIGHT, R_PWM, R_DIR, R_ENCA};

    Pose true_pose = {START_X, START_Y, START_THETA};
    double duration = DURATION;
    if (recalage) {
        true_pose = {TRUE_START_X, TRUE_START_Y, TRUE_START_THETA};
        robot.init_rolling_basis(BELIEVED_START_X, BELIEVED_START_Y,
                                 BELIEVED_START_THETA);
        robot.push_until_blocked(PUSH_SPEED, PUSH_MAX_DISTANCE);
        duration = RECALAGE_DURATION;
        print_pose_error("depart", robot, true_pose);
    } else {
        robot.init_rolling_basis(START_X, START_Y, START_THETA);
        robot.set_target(Point(TARGET_X, TARGET_Y, TARGET_THETA));
    }

    // étapes jouées par la Raspberry pendant le recalage
    enum class Step {
        PUSH_BOTTOM,
        CLEAR_BOTTOM,
        TURN,
        PUSH_LEFT,
        CLEAR_LEFT,
        DONE
    };
    Step step = Step::PUSH_BOTTOM;
    bool refused_tested = false;

    char path[64];
    snprintf(path, sizeof(path), "tmp/%s.csv", scenario);
    FILE* csv = fopen(path, "w");
    if (csv == nullptr) {
        printf("Impossible d'ouvrir %s\n", path);
        return 1;
    }
    fprintf(csv,
            "t,delta_c,delta_mes,psi_c,psi_mes,v_left_c,v_left,v_right_c,"
            "v_right,u_left,u_right,x,y,theta,step,x_true,y_true,theta_true\n");

    double end_time = -1.0;
    for (int i = 0; i * TS < duration; i++) {
        double t = i * TS;

        // même ordre que le timer de la Teensy
        robot.odometrie_handle();
        robot.handle();

        // écrit avant de bouger les roues : l'odométrie vient d'être lue, la
        // pose réelle doit être celle du même instant
        fprintf(csv,
                "%.3f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%d,%f,%f,%f\n", t,
                robot.delta_profile.position, robot.delta_mes,
                robot.psi_profile.position, robot.psi_mes, robot.v_left_target,
                robot.left_motor->speed, robot.v_right_target,
                robot.right_motor->speed, robot.left_motor->voltage,
                robot.right_motor->voltage, robot.X, robot.Y, robot.THETA,
                (int)robot.move_step, true_pose.x, true_pose.y,
                true_pose.theta);

        bool blocked = block_left && t >= BLOCK_START;
        bool wall_left = recalage && rear_corner_on_wall(true_pose, 1.0);
        bool wall_right = recalage && rear_corner_on_wall(true_pose, -1.0);
        double left_before = left.distance;
        double right_before = right.distance;
        update_wheel(left, robot.wheel_unit_tick_cm(), blocked, wall_left);
        update_wheel(right, robot.wheel_unit_tick_cm(), false, wall_right);
        update_true_pose(true_pose, left.distance - left_before,
                         right.distance - right_before);

        if (!recalage) {
            if (end_time < 0.0 &&
                robot.move_step == Rolling_Basis::MoveStep::IDLE) {
                end_time = t;
            }
            continue;
        }

        // ce que ferait la Raspberry en lisant le statut de la Teensy
        Rolling_Basis::Status status = robot.get_status();

        // un recalage pendant la poussée doit être refusé
        if (!refused_tested && t >= 0.5) {
            bool applied = robot.reset_pose(Point(0.0, 0.0, 0.0));
            printf("[recalage] reset pendant la poussee : %s\n",
                   applied ? "APPLIQUE (erreur)" : "refuse");
            refused_tested = true;
        }

        if (status == Rolling_Basis::Status::STOPPED &&
            (step == Step::PUSH_BOTTOM || step == Step::PUSH_LEFT)) {
            printf("[recalage] %.2f s : aucune bordure touchee\n", t);
            break;
        }

        switch (step) {
            case Step::PUSH_BOTTOM:
                if (status == Rolling_Basis::Status::BLOCKED) {
                    print_pose_error("contre la bordure du bas, avant reset",
                                     robot, true_pose);
                    // y et theta donnés par la bordure, x gardé
                    robot.reset_pose(Point(robot.X, D_BACK, PI / 2));
                    print_pose_error("apres reset", robot, true_pose);
                    robot.set_target(
                        Point(robot.X, D_BACK + CLEARANCE, PI / 2));
                    step = Step::CLEAR_BOTTOM;
                }
                break;

            case Step::CLEAR_BOTTOM:
                if (status == Rolling_Basis::Status::STOPPED) {
                    // tourner sur place pour présenter l'arrière à gauche
                    robot.set_target(Point(robot.X, robot.Y, 0.0));
                    step = Step::TURN;
                }
                break;

            case Step::TURN:
                if (status == Rolling_Basis::Status::STOPPED) {
                    robot.push_until_blocked(PUSH_SPEED, PUSH_MAX_DISTANCE);
                    step = Step::PUSH_LEFT;
                }
                break;

            case Step::PUSH_LEFT:
                if (status == Rolling_Basis::Status::BLOCKED) {
                    print_pose_error("contre la bordure de gauche, avant reset",
                                     robot, true_pose);
                    // x et theta donnés par la bordure, y gardé
                    robot.reset_pose(Point(D_BACK, robot.Y, 0.0));
                    print_pose_error("apres reset", robot, true_pose);
                    robot.set_target(Point(D_BACK + CLEARANCE, robot.Y, 0.0));
                    step = Step::CLEAR_LEFT;
                }
                break;

            case Step::CLEAR_LEFT:
                if (status == Rolling_Basis::Status::STOPPED) {
                    end_time = t;
                    step = Step::DONE;
                }
                break;

            case Step::DONE:
                break;
        }
    }
    fclose(csv);

    if (recalage) {
        printf("[recalage] fin du recalage : %.2f s\n", end_time);
        print_pose_error("final", robot, true_pose);
        printf("[recalage] pose reelle : x = %.2f cm, y = %.2f cm, "
               "theta = %.2f deg\n",
               true_pose.x, true_pose.y, true_pose.theta * 180.0 / PI);
        return step == Step::DONE ? 0 : 1;
    }

    printf("[%s] fin du mouvement : %.2f s, statut : %d\n", scenario, end_time,
           (int)robot.get_status());
    printf("[%s] x = %.2f cm, y = %.2f cm, theta = %.3f rad\n", scenario,
           robot.X, robot.Y, robot.THETA);
    return 0;
}
