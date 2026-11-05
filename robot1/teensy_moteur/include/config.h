/*
 * This file is dedicated to the configuration of the robot: all the constants
 * and the pinout are defined here.
 */

// Default position
#define START_X 0.0
#define START_Y 0.0
#define START_THETA 0.0

// Motor Left
#define L_ENCA 12
#define L_ENCB 11
#define L_PWM 5
#define L_DIR 4  // a changer surement

// Motor Right
#define R_ENCA 14
#define R_ENCB 13
#define R_PWM 2
#define R_DIR 0  // a changer surement

// Encoder
#define ENCODER_RESOLUTION 4096 //comme on a 4 ticks par impulsions, on aura 4*1024 = 4096 ticks par tour comme résolution
#define ENTRAXE 29.5
#define WHEEL_DIAMETER 5.9

// PIs for each wheels
#define KP_SPEED_LEFT 0
#define KI_SPEED_LEFT 0

#define KP_SPEED_RIGHT 0
#define KI_SPEED_RIGHT 0

// Niveau 2 de l'asservissement
#define KP_LINEAR_POSITION 0

#define KP_ANGULAR_POSITION 0

// PID IDS
#define LINEAR_POSITION_PID_ID 0
#define ANGULAR_POSITION_PID_ID 1
#define LEFT_SPEED_PID_ID 2
#define RIGHT_SPEED_PID_ID 3

// PWM
#define PWM_FREQUENCY 40000
#define PWM_RESOLUTION 12
#define PWM_MAX 4095  // (2 ** PWM_RESOLUTION) - 1

// Asservissement echantillonage fréquence
#define ASSERVISSEMENT_PERIOD 5000         // 5ms
#define TS (ASSERVISSEMENT_PERIOD * 1e-6)  // en s

// Com baudrate
#define BAUDRATE 115200

// Tension
#define U_MAX 12.0  // en V
#define U_MIN 0.0 // zone morte : tension min pour que la roue démarre, à mesurer
#define VBAT_DEFAULT 14.8  // la tension de la batterie par default

// SPEED AND TURN LIMIT
#define V_MAX 20.0     // en cm/s
#define ACC_MAX 15.0   // en cm/s²
#define W_MAX 1.0      // en rad/s
#define W_ACC_MAX 1.0  // en rad/s²

// Arrivée d'un mouvement
#define POSITION_TOLERANCE 0.2  // en cm
#define ANGLE_TOLERANCE 0.01    // en rad

// Détection de blocage
#define BLOCK_VOLTAGE 8.0  // en V
#define BLOCK_SPEED 1.0    // en cm/s
#define BLOCK_PERIODS 100  // 0,5 s à 200 Hz