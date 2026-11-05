// Remplace la librairie Encoder : les tics viennent du moteur simulé
#ifndef FAKE_ENCODER_H
#define FAKE_ENCODER_H

#include <Arduino.h>

class Encoder {
   public:
    Encoder(byte pin_a, byte pin_b) : pin(pin_a) {}
    long read() { return fake_ticks[this->pin]; }

   private:
    byte pin;
};

#endif  // FAKE_ENCODER_H
