/**
 * Trapezoidal speed profile, starting from any speed.
 *
 * Three phases: from v_start to v_peak at a_max (acceleration, or braking if
 * v_start is above v_max), cruise at v_peak, braking to zero at a_max.
 */

#include "trapezoid.h"
#include <math.h>

Trapezoid::Trapezoid(double v_max, double a_max) : v_max(v_max), a_max(a_max) {}

void Trapezoid::set_limits(double v_max, double a_max) {
    this->v_max = v_max;
    this->a_max = a_max;
}

void Trapezoid::start(double start, double distance, double initial_speed) {
    this->origin = start;
    this->position = start;
    this->t = 0.0;

    if (distance != 0.0) {
        this->direction = distance > 0.0 ? 1.0 : -1.0;
    } else {
        this->direction = initial_speed >= 0.0 ? 1.0 : -1.0;
    }
    this->length = fabs(distance);

    // a speed in the other direction, or too high to stop in time, is not
    // possible here: the caller checks can_reach() first
    double v0 = fmax(initial_speed * this->direction, 0.0);
    this->v_start = fmin(v0, sqrt(2.0 * this->a_max * this->length));

    // highest speed that still leaves room to brake to zero at the end:
    // (v_peak² - v_start²) / 2a + v_peak² / 2a = length
    this->v_peak =
        fmin(this->v_max, sqrt(this->a_max * this->length +
                               this->v_start * this->v_start / 2.0));

    this->t_change = fabs(this->v_peak - this->v_start) / this->a_max;
    this->d_change = (this->v_start + this->v_peak) / 2.0 * this->t_change;

    double d_brake = this->v_peak * this->v_peak / (2.0 * this->a_max);
    double d_cruise = fmax(this->length - this->d_change - d_brake, 0.0);
    double t_cruise = this->v_peak > 0.0 ? d_cruise / this->v_peak : 0.0;

    this->t_brake = this->t_change + t_cruise;
    this->t_total = this->t_brake + this->v_peak / this->a_max;
    this->speed = this->direction * this->v_start;
}

bool Trapezoid::can_reach(double distance) const {
    if (this->speed == 0.0) {
        return true;
    }
    if (this->speed * distance < 0.0) {
        return false;
    }
    double braking = this->speed * this->speed / (2.0 * this->a_max);
    // a tiny margin for the rounding of the braking distance
    return braking <= fabs(distance) + 1e-9;
}

void Trapezoid::stop() {
    double braking = this->speed * this->speed / (2.0 * this->a_max);
    this->start(this->position, this->speed >= 0.0 ? braking : -braking,
                this->speed);
}

void Trapezoid::step(double ts) {
    this->t += ts;

    // end of the move: stay exactly on the target
    if (this->finished()) {
        this->position = this->origin + this->direction * this->length;
        this->speed = 0.0;
        return;
    }

    double v;  // speed at this time
    double s;  // distance travelled since the start

    if (this->t < this->t_change) {
        double sign = this->v_peak >= this->v_start ? 1.0 : -1.0;
        v = this->v_start + sign * this->a_max * this->t;
        s = this->v_start * this->t +
            sign * 0.5 * this->a_max * this->t * this->t;
    } else if (this->t < this->t_brake) {
        v = this->v_peak;
        s = this->d_change + this->v_peak * (this->t - this->t_change);
    } else {
        // braking: count the time left before the end
        double t_left = this->t_total - this->t;
        v = this->a_max * t_left;
        s = this->length - 0.5 * this->a_max * t_left * t_left;
    }

    this->position = this->origin + this->direction * s;
    this->speed = this->direction * v;
}

bool Trapezoid::finished() const {
    return this->t >= this->t_total;
}
