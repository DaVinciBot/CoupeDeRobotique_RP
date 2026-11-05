// Fait tourner le vrai code de la base roulante avec des moteurs simulés.
// Seul le matériel est remplacé (dossier fake). Lancer avec run.ps1.
//
// Usage : simulation.exe normal|blocage

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

const int SUB_STEPS = 50;  // calculs du moteur par période de la boucle

struct Wheel {
    double k;
    byte pin_pwm;
    byte pin_dir;
    byte pin_enca;
    double speed = 0.0;     // en cm/s
    double distance = 0.0;  // en cm
};

// Calcule une période du moteur à partir des broches écrites par le code
void update_wheel(Wheel& wheel, double tick_cm, bool blocked) {
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
        if (blocked) {
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
                        BLOCK_VOLTAGE, BLOCK_SPEED, BLOCK_PERIODS);
    robot.define_right_motor(R_ENCA, R_ENCB, R_PWM, R_DIR, PWM_MAX, U_MAX, TS);
    robot.define_left_motor(L_ENCA, L_ENCB, L_PWM, L_DIR, PWM_MAX, U_MAX, TS);
    robot.init_motors();
    robot.init_rolling_basis(START_X, START_Y, START_THETA);
    robot.vbat = VBAT_DEFAULT;

    Wheel left = {K_LEFT, L_PWM, L_DIR, L_ENCA};
    Wheel right = {K_RIGHT, R_PWM, R_DIR, R_ENCA};

    robot.set_target(Point(TARGET_X, TARGET_Y, TARGET_THETA));

    char path[64];
    snprintf(path, sizeof(path), "tmp/%s.csv", scenario);
    FILE* csv = fopen(path, "w");
    if (csv == nullptr) {
        printf("Impossible d'ouvrir %s\n", path);
        return 1;
    }
    fprintf(csv,
            "t,delta_c,delta_mes,psi_c,psi_mes,v_left_c,v_left,v_right_c,"
            "v_right,u_left,u_right,x,y,theta,step\n");

    double end_time = -1.0;
    for (int i = 0; i * TS < DURATION; i++) {
        double t = i * TS;

        // même ordre que le timer de la Teensy
        robot.odometrie_handle();
        robot.handle();

        bool blocked = block_left && t >= BLOCK_START;
        update_wheel(left, robot.wheel_unit_tick_cm(), blocked);
        update_wheel(right, robot.wheel_unit_tick_cm(), false);

        fprintf(csv, "%.3f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%d\n", t,
                robot.delta_profile.position, robot.delta_mes,
                robot.psi_profile.position, robot.psi_mes, robot.v_left_target,
                robot.left_motor->speed, robot.v_right_target,
                robot.right_motor->speed, robot.left_motor->voltage,
                robot.right_motor->voltage, robot.X, robot.Y, robot.THETA,
                (int)robot.move_step);

        if (end_time < 0.0 &&
            robot.move_step == Rolling_Basis::MoveStep::IDLE) {
            end_time = t;
        }
    }
    fclose(csv);

    printf("[%s] fin du mouvement : %.2f s, statut : %d\n", scenario, end_time,
           (int)robot.get_status());
    printf("[%s] x = %.2f cm, y = %.2f cm, theta = %.3f rad\n", scenario,
           robot.X, robot.Y, robot.THETA);
    return 0;
}
