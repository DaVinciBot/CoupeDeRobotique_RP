// Remplace Arduino.h pour compiler le code du robot sur PC
#ifndef FAKE_ARDUINO_H
#define FAKE_ARDUINO_H

#include <math.h>

#define PI 3.14159265358979
#define OUTPUT 1

typedef unsigned char byte;

// état des broches, lu par le moteur simulé
inline int fake_pwm[64];
inline int fake_dir[64];
inline long fake_ticks[64];

inline void pinMode(int pin, int mode) {}
inline void digitalWrite(int pin, int value) {
    fake_dir[pin] = value;
}
inline void analogWrite(int pin, int value) {
    fake_pwm[pin] = value;
}

#endif  // FAKE_ARDUINO_H
