/**
 * This is the implementation of the Trapezoid class.
 * The Trapezoid class generates the position and speed setpoints of a move.
 */

#include "trapezoid.h"
#include <math.h>

Trapezoid::Trapezoid(double v_max, double a_max) : v_max(v_max), a_max(a_max) {}

void Trapezoid::start(double start, double distance) {
    this->origin = start;
    this->position = start;
    this->speed = 0.0;
    this->direction = distance >= 0.0 ? 1.0 : -1.0;
    this->length = fabs(distance);
    this->t = 0.0;

    // sur une distance courte, on n'a pas le temps d'atteindre v_max
    this->v_peak = fmin(this->v_max, sqrt(this->length * this->a_max));
    this->t_acc = this->v_peak / this->a_max;

    double d_acc = this->v_peak * this->v_peak / (2.0 * this->a_max);
    double t_cruise = 0.0;
    if (this->v_peak > 0.0) {
        t_cruise = (this->length - 2.0 * d_acc) / this->v_peak;
    }
    this->t_total = 2.0 * this->t_acc + t_cruise;
}

void Trapezoid::step(double ts) {
    this->t += ts;

    // fin du mouvement : on reste exactement sur la cible
    if (this->finished()) {
        this->position = this->origin + this->direction * this->length;
        this->speed = 0.0;
        return;
    }

    double v;  // vitesse à cet instant
    double s;  // distance parcourue depuis le départ
    double t_brake = this->t_total - this->t_acc;

    if (this->t < this->t_acc) {
        // accélération
        v = this->a_max * this->t;
        s = 0.5 * this->a_max * this->t * this->t;
    } else if (this->t < t_brake) {
        // vitesse constante
        v = this->v_peak;
        s = 0.5 * this->v_peak * this->t_acc +
            this->v_peak * (this->t - this->t_acc);
    } else {
        // freinage : on compte le temps qu'il reste avant la fin
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
