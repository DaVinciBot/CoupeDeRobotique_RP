#ifndef TRAPEZOID_H
#define TRAPEZOID_H

/**
 * @brief Générateur de consigne en trapèze de vitesse
 *
 * Accélère, roule à vitesse constante puis freine pour arriver pile à la
 * cible. Si la distance est trop courte, le trapèze devient un triangle.
 */
class Trapezoid {
   public:
    double position = 0.0;  // consigne de position à l'instant courant
    double speed = 0.0;     // vitesse prévue, utilisée pour l'anticipation

    Trapezoid(double v_max, double a_max);

    /**
     * @brief Prépare un nouveau mouvement
     *
     * @param start Position de départ
     * @param distance Distance à parcourir, négative pour reculer
     */
    void start(double start, double distance);

    /**
     * @brief Avance le profil d'une période
     *
     * @param ts Période de la boucle, en s
     */
    void step(double ts);

    bool finished() const;

   private:
    double v_max;
    double a_max;

    double origin = 0.0;     // position de départ
    double direction = 1.0;  // +1 en avant, -1 en arrière
    double length = 0.0;     // distance à parcourir, toujours positive
    double v_peak = 0.0;     // vitesse la plus haute du mouvement
    double t_acc = 0.0;      // durée de l'accélération, en s
    double t_total = 0.0;    // durée totale, en s
    double t = 0.0;          // temps écoulé, en s
};

#endif  // TRAPEZOID_H
