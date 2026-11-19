#ifndef TRAPEZOID_H
#define TRAPEZOID_H

/**
 * @brief Trapezoidal speed profile generator
 *
 * Goes from the initial speed to the peak speed, cruises, then brakes to stop
 * exactly on the target. On a short distance the trapezoid becomes a
 * triangle. Units are those of the caller (m and m/s, or rad and rad/s).
 */
class Trapezoid {
   public:
    double position = 0.0;  // position setpoint at the current time
    double speed = 0.0;     // planned speed, used as feedforward

    Trapezoid(double v_max, double a_max);

    /**
     * @brief Changes the limits used by the next start() or stop()
     */
    void set_limits(double v_max, double a_max);

    /**
     * @brief Plans a new move
     *
     * The initial speed must have the sign of distance (or be zero) and the
     * robot must be able to stop within distance: see can_reach().
     *
     * @param start Start position
     * @param distance Distance to travel, negative to go backwards
     * @param initial_speed Speed at the start, signed
     */
    void start(double start, double distance, double initial_speed = 0.0);

    /**
     * @brief True if start(position, distance, speed) is possible: same
     * direction as the current speed, and enough room to brake
     */
    bool can_reach(double distance) const;

    /**
     * @brief Brakes from the current speed at a_max, down to zero
     */
    void stop();

    /**
     * @brief Advances the profile by one period
     *
     * @param ts Loop period, in s
     */
    void step(double ts);

    bool finished() const;

   private:
    double v_max;
    double a_max;

    double origin = 0.0;     // start position
    double direction = 1.0;  // +1 forwards, -1 backwards
    double length = 0.0;     // distance to travel, always positive
    double v_start = 0.0;    // initial speed along direction, >= 0
    double v_peak = 0.0;     // cruise speed
    double t_change = 0.0;   // duration from v_start to v_peak, in s
    double d_change = 0.0;   // distance from v_start to v_peak
    double t_brake = 0.0;    // time when the final braking starts, in s
    double t_total = 0.0;    // total duration, in s
    double t = 0.0;          // elapsed time, in s
};

#endif  // TRAPEZOID_H
