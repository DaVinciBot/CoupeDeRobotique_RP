// Runs the real control code of the rolling base on simulated motors
// (plant.h). Run it with run.ps1.
//
// Usage: simulation.exe normal|blocage|recalage

#include <motion_controller.h>
#include <stdio.h>
#include <string.h>
#include "plant.h"

using namespace motion;

const double DURATION = 15.0;             // s
const double BLOCK_START = 4.0;           // left wheel blocked from here, s
const double RECALIBRATION_DURATION = 40.0;  // s
const double PUSH_SPEED = 0.05;           // m/s
const double PUSH_DISTANCE = -0.4;        // backwards, m
const double CLEARANCE = 0.08;            // move away from the border, m

double angle_error(double a, double b) {
    return normalize_angle(a - b);
}

void print_pose_error(const char* label,
                      const MotionController& controller,
                      const sim::Plant& plant) {
    Pose pose = controller.status().pose;
    printf("[recalage] %s : erreur x = %+.2f mm, y = %+.2f mm, theta = %+.2f deg\n",
           label, (pose.x - plant.pose.x) * 1000, (pose.y - plant.pose.y) * 1000,
           angle_error(pose.theta, plant.pose.theta) * 180.0 / kPi);
}

MoveCommand push_command(uint16_t id) {
    MoveCommand c;
    c.id = id;
    c.kind = MoveKind::PUSH_UNTIL_BLOCKED;
    c.distance = PUSH_DISTANCE;
    c.max_speed = PUSH_SPEED;
    return c;
}

MoveCommand goto_command(uint16_t id, double x, double y, double theta) {
    MoveCommand c;
    c.id = id;
    c.kind = MoveKind::GOTO;
    c.flags = move_flags::HAS_HEADING;
    c.x = x;
    c.y = y;
    c.theta = theta;
    return c;
}

int main(int argc, char** argv) {
    const char* scenario = argc > 1 ? argv[1] : "normal";
    bool block_left = strcmp(scenario, "blocage") == 0;
    bool recalibration = strcmp(scenario, "recalage") == 0;

    MotionController controller(sim::config(), sim::TS);
    controller.set_params(sim::params());
    controller.heartbeat();
    sim::Plant plant;

    double duration = DURATION;
    if (recalibration) {
        plant.walls = true;
        // real pose, and the pose the robot believes: 3 cm and 3° off
        plant.pose = {0.30, 0.22, kPi / 2 + 0.05};
        controller.reset_pose({0.27, 0.25, kPi / 2});
        controller.move(push_command(1));
        duration = RECALIBRATION_DURATION;
        print_pose_error("depart", controller, plant);
    } else {
        controller.move(goto_command(1, 0.5, 0.5, kPi / 2));
    }

    // steps played by the brain during the recalibration
    enum class Step { PUSH_BOTTOM, CLEAR_BOTTOM, PUSH_LEFT, CLEAR_LEFT, DONE };
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
            "v_right,u_left,u_right,x,y,theta,state,x_true,y_true,theta_true\n");

    double end_time = -1.0;
    Outputs u = {0.0, 0.0};
    for (int i = 0; i * sim::TS < duration; i++) {
        double t = i * sim::TS;
        if (i % 10 == 0) {
            controller.heartbeat();
        }

        u = controller.step(plant.inputs());
        Status status = controller.status();

        // written before moving the wheels: the odometry has just been
        // read, the real pose must be the one of the same time
        fprintf(csv, "%.3f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%d,%f,%f,%f\n",
                t, controller.distance_setpoint(),
                controller.travelled_distance(), controller.angle_setpoint(),
                controller.travelled_angle(), controller.left_speed_target(),
                controller.left_speed(), controller.right_speed_target(),
                controller.right_speed(), u.u_left, u.u_right, status.pose.x,
                status.pose.y, status.pose.theta, (int)status.state,
                plant.pose.x, plant.pose.y, plant.pose.theta);

        plant.left.blocked = block_left && t >= BLOCK_START;
        plant.apply(u);

        if (!recalibration) {
            if (end_time < 0.0 && status.state != MotionState::MOVING) {
                end_time = t;
            }
            continue;
        }

        // a recalibration during the push must be refused
        if (!refused_tested && t >= 0.5) {
            bool applied = controller.reset_pose({0.0, 0.0, 0.0});
            printf("[recalage] reset pendant la poussee : %s\n",
                   applied ? "APPLIQUE (erreur)" : "refuse");
            refused_tested = true;
        }

        if (status.state == MotionState::ARRIVED &&
            (step == Step::PUSH_BOTTOM || step == Step::PUSH_LEFT)) {
            printf("[recalage] %.2f s : aucune bordure touchee\n", t);
            break;
        }

        Pose pose = status.pose;
        switch (step) {
            case Step::PUSH_BOTTOM:
                if (status.state == MotionState::BLOCKED) {
                    print_pose_error("contre la bordure du bas, avant reset",
                                     controller, plant);
                    // y and theta given by the border, x kept
                    controller.reset_pose({pose.x, sim::D_BACK, kPi / 2});
                    print_pose_error("apres reset", controller, plant);
                    // move away, then present the rear to the left border
                    controller.move(goto_command(2, pose.x,
                                                 sim::D_BACK + CLEARANCE, 0.0));
                    step = Step::CLEAR_BOTTOM;
                }
                break;

            case Step::CLEAR_BOTTOM:
                if (status.state == MotionState::ARRIVED) {
                    controller.move(push_command(3));
                    step = Step::PUSH_LEFT;
                }
                break;

            case Step::PUSH_LEFT:
                if (status.state == MotionState::BLOCKED) {
                    print_pose_error("contre la bordure de gauche, avant reset",
                                     controller, plant);
                    // x and theta given by the border, y kept
                    controller.reset_pose({sim::D_BACK, pose.y, 0.0});
                    print_pose_error("apres reset", controller, plant);
                    controller.move(goto_command(4, sim::D_BACK + CLEARANCE,
                                                 pose.y, 0.0));
                    step = Step::CLEAR_LEFT;
                }
                break;

            case Step::CLEAR_LEFT:
                if (status.state == MotionState::ARRIVED) {
                    end_time = t;
                    step = Step::DONE;
                }
                break;

            case Step::DONE:
                break;
        }
    }
    fclose(csv);

    Status status = controller.status();
    if (recalibration) {
        printf("[recalage] fin du recalage : %.2f s\n", end_time);
        print_pose_error("final", controller, plant);
        printf("[recalage] pose reelle : x = %.1f mm, y = %.1f mm, "
               "theta = %.2f deg\n",
               plant.pose.x * 1000, plant.pose.y * 1000,
               plant.pose.theta * 180.0 / kPi);
        return step == Step::DONE ? 0 : 1;
    }

    printf("[%s] fin du mouvement : %.2f s, statut : %d\n", scenario, end_time,
           (int)status.state);
    printf("[%s] x = %.1f mm, y = %.1f mm, theta = %.3f rad\n", scenario,
           status.pose.x * 1000, status.pose.y * 1000, status.pose.theta);
    return 0;
}
