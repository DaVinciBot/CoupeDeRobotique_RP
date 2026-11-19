#ifndef PID_H
#define PID_H

#include <math.h>

/**
 * @brief Fixed period corrector, used by every loop of the rolling base
 *
 * - The speed PIs use kp and ki: their output is a voltage.
 * - The position Ps have ki = 0: their output is a speed.
 * - No derivative term: on a first order system it only amplifies the noise
 *   of the encoders (section 7 of the control design document).
 * - The integral does not move while the output is saturated.
 */
class PID {
   public:
    /**
     * @param kp            Proportional gain
     * @param ki            Integral gain
     * @param minOutput     Lowest output
     * @param maxOutput     Highest output
     * @param ts            Loop period, in s
     */
    PID(double kp, double ki, double minOutput, double maxOutput, double ts);

    /**
     * @brief Changes the gains without touching the integral
     */
    void setTunings(double kp, double ki);

    /**
     * @brief Changes the output limits, ignored if min >= max
     */
    void setOutputLimits(double minOutput, double maxOutput);

    /**
     * @brief Changes the loop period, in s
     */
    void setPeriod(double ts);

    /**
     * @brief Command from the error
     *
     * The output is kp * error + integral, limited to [minOutput, maxOutput]
     * and to [-limit, limit]. The integral only grows when the output is not
     * saturated. To be called once per period.
     *
     * @param error  Error (setpoint - measurement)
     * @param limit  Extra limit of the output, for this call
     * @return Limited command
     */
    double compute(double error, double limit = INFINITY);

    /**
     * @brief Sets the integral back to zero
     */
    void reset();

   private:
    double _kp, _ki;
    double _minOutput, _maxOutput;
    double _integral;  // sum of ki * error * ts
    double _ts;        // loop period, in s
};

#endif  // PID_H
