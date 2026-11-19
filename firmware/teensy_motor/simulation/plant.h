/**
 * Simulated rolling base, shared by the simulation and the native tests.
 *
 * Each wheel is the first order model of the control design document
 * (section 5): tau * dv/dt = K * u - v, with a dead zone for the dry
 * friction. The encoders only see whole counts, as on the robot. The values
 * are examples: replace them with the identification results (section 8).
 */

#ifndef SIMULATION_PLANT_H
#define SIMULATION_PLANT_H

#include <math.h>
#include <motion_controller.h>

namespace sim {

// Example robot, close to the 2026 robot
const double TICK_DISTANCE = motion::kPi * 0.059 / 4096;  // m per count
const double TRACK_WIDTH = 0.295;                         // m
const double TS = 0.005;                                  // s

const double K_LEFT = 0.05;    // final speed per volt, m/s/V
const double K_RIGHT = 0.045;  // a bit weaker on the right, on purpose
const double TAU = 0.1;        // motor time constant, s
const double DEAD_ZONE = 1.0;  // voltage lost in the dry friction, V

// Rear of the robot, for the pushes against the borders
const double D_BACK = 0.12;      // wheel axis -> rear face, m
const double HALF_WIDTH = 0.15;  // half width of the rear face, m

inline motion::Config config() {
    motion::Config c;
    c.tick_distance = TICK_DISTANCE;
    c.track_width = TRACK_WIDTH;
    c.u_max = 12.0;
    c.heartbeat_timeout = 0.2;
    c.max_trace_duration = 10.0;
    c.continue_angle = 10.0 * motion::kPi / 180.0;
    return c;
}

// Gains from the design document: Kp = tau / (K * tau_v), Ki = Kp / tau
// (7.1), position gain 0.5 / tau_v (7.2)
inline motion::ControlParams params() {
    const double tau_v = 0.05;
    motion::ControlParams p;
    p.left_speed_kp = TAU / (K_LEFT * tau_v);
    p.left_speed_ki = p.left_speed_kp / TAU;
    p.right_speed_kp = TAU / (K_RIGHT * tau_v);
    p.right_speed_ki = p.right_speed_kp / TAU;
    p.distance_kp = 0.5 / tau_v;
    p.heading_kp = 0.5 / tau_v;
    p.max_speed = 0.2;
    p.max_accel = 0.15;
    p.max_angular_speed = 1.0;
    p.max_angular_accel = 1.0;
    p.position_tolerance = 0.002;
    p.angle_tolerance = 0.01;
    p.block_voltage = 8.0;
    p.block_speed = 0.01;
    p.block_time = 0.5;
    p.push_voltage = 4.0;
    p.loop_period = TS;
    return p;
}

struct Wheel {
    double k;
    double speed = 0.0;     // m/s
    double distance = 0.0;  // m
    bool blocked = false;   // held by an obstacle

    explicit Wheel(double k) : k(k) {}
};

class Plant {
   public:
    Wheel left{K_LEFT};
    Wheel right{K_RIGHT};
    motion::Pose pose;   // real pose, unknown to the controller
    bool walls = false;  // borders at x = 0 and y = 0 stop the rear corners
    bool emergency_stop = false;
    double vbat = 14.8;

    motion::Inputs inputs() const {
        return {(int32_t)floor(this->left.distance / TICK_DISTANCE),
                (int32_t)floor(this->right.distance / TICK_DISTANCE),
                this->vbat, this->emergency_stop};
    }

    // Applies the voltages during one period
    void apply(const motion::Outputs& u) {
        // the emergency stop cuts the power of the drivers (R1)
        double u_left = this->emergency_stop ? 0.0 : u.u_left;
        double u_right = this->emergency_stop ? 0.0 : u.u_right;
        bool wall_left = this->walls && this->rear_corner_on_wall(1.0);
        bool wall_right = this->walls && this->rear_corner_on_wall(-1.0);

        double d_left = this->update_wheel(this->left, u_left, wall_left);
        double d_right = this->update_wheel(this->right, u_right, wall_right);

        double d = (d_left + d_right) / 2.0;
        double d_theta = (d_right - d_left) / TRACK_WIDTH;
        this->pose.x += cos(this->pose.theta + d_theta / 2.0) * d;
        this->pose.y += sin(this->pose.theta + d_theta / 2.0) * d;
        this->pose.theta = motion::normalize_angle(this->pose.theta + d_theta);
    }

   private:
    // True if the rear left (side = 1) or right (side = -1) corner touches
    // the border y = 0 or x = 0
    bool rear_corner_on_wall(double side) const {
        double x = this->pose.x - D_BACK * cos(this->pose.theta) -
                   side * HALF_WIDTH * sin(this->pose.theta);
        double y = this->pose.y - D_BACK * sin(this->pose.theta) +
                   side * HALF_WIDTH * cos(this->pose.theta);
        return x <= 0.0 || y <= 0.0;
    }

    // Returns the distance travelled by the wheel during the period
    static double update_wheel(Wheel& wheel, double u, bool wall) {
        const int sub_steps = 50;
        double useful = fmax(fabs(u) - DEAD_ZONE, 0.0);
        double u_effective = u >= 0.0 ? useful : -useful;

        double before = wheel.distance;
        double dt = TS / sub_steps;
        for (int i = 0; i < sub_steps; i++) {
            wheel.speed += dt * (wheel.k * u_effective - wheel.speed) / TAU;
            // against the border, the wheel cannot go backwards any more
            if (wheel.blocked || (wall && wheel.speed < 0.0)) {
                wheel.speed = 0.0;
            }
            wheel.distance += wheel.speed * dt;
        }
        return wheel.distance - before;
    }
};

}  // namespace sim

#endif  // SIMULATION_PLANT_H
