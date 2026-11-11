#ifndef PID_H
#define PID_H

#include <Arduino.h>

/**
 * @brief Correcteur à période fixe, utilisé pour tous les asservissements
 *
 * - Les PI de vitesse utilisent kp et ki : leur sortie est une tension.
 * - Les P de position ont ki = 0 : leur sortie est une vitesse.
 * - kd est gardé pour le message SET_PID, mais il n'est pas utilisé.
 * - L'intégrale n'avance pas quand la sortie est saturée.
 */
class PID {
   public:
    /**
     * @param kp            Gain proportionnel
     * @param ki            Gain intégral
     * @param kd            Gain dérivé (non utilisé)
     * @param minOutput     Valeur minimale de la sortie
     * @param maxOutput     Valeur maximale de la sortie
     * @param ts            Période de la boucle, en s
     */
    PID(double kp,
        double ki,
        double kd,
        double minOutput,
        double maxOutput,
        double ts);

    /**
     * @brief Change les gains et remet l'intégrale à zéro
     */
    void updateParameters(double kp, double ki, double kd);

    /**
     * @brief Change les gains sans toucher à l'intégrale
     */
    void setTunings(double kp, double ki, double kd);

    /**
     * @brief Change les bornes de la sortie, ignorées si min >= max
     */
    void setOutputLimits(double minOutput, double maxOutput);

    /**
     * @brief Calcule la commande à partir de l'erreur
     *
     * La sortie vaut kp * error + intégrale, bornée entre minOutput et
     * maxOutput. L'intégrale avance seulement si la sortie n'est pas saturée.
     * A appeler une seule fois par période.
     *
     * @param error  Erreur (consigne - mesure)
     * @return Commande bornée entre minOutput et maxOutput
     */
    double compute(double error);

    /**
     * @brief Remet l'intégrale à zéro
     */
    void reset();

   private:
    double _kp, _ki, _kd;
    double _minOutput, _maxOutput;
    double _integral;  // somme des ki * error * ts
    double _ts;        // période de la boucle, en s
};

#endif  // PID_H
