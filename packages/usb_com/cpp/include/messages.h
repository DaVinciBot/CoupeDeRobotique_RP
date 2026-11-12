#pragma pack(1)
// dans nos structures, nous avons des variables plus petites que la taille
// défaut du processeur (processeur 32 bits et variables 8 bits de type byte)
// cela indique au compilateur de ne pas ajouter de padding entre les variables
// (pack(1) indique que la taille de l'alignement est de 1 octet)

#include <Arduino.h>

// ====== USB Communication Signature ======
// This signature must be exactly the same on both sides (Raspberry Pi and Teensy) to ensure valid communication.
const byte END_BYTES_SIGNATURE[4] = {0xBA, 0xDD, 0x1C, 0xC5};

// ====== Message Types ======
/* Definition of message IDs */
// rasp -> teensy : 0-127 (Convention)

// Rolling Basis
#define SET_TARGET_POSITION 0
#define SET_PID 1
#define RESET_POSE 2
#define SET_MOTORS_VOLTAGE 9
#define SET_WHEELS_SPEED 10
#define PUSH_UNTIL_BLOCKED 11

// Actuators
#define SET_SERVO_ANGLE_I2C 3
#define STEPPER_STEP 4
#define SET_SERVO_ANGLE_DETACH 5
#define ATTACH_SWITCH 6
#define SET_SERVO_ANGLE 7
#define SET_STEPPER_DRIVER_ACTIVATION_STATE 8

// Common (Rolling Basis + Actuators)
#define RESET_TEENSY 126

// two ways : 127 (Convention)
#define NACK 127

// teensy -> rasp : 128-255 (Convention)
// Rolling Basis
#define UPDATE_ROLLING_BASIS 128
#define UPDATE_SPEEDS 130

// Actuators
#define SWITCH_STATE_RETURN 129

// Common (Rolling Basis + Actuators)
#define PRINT 254
#define UNKNOWN_MSG_TYPE 255

/* Definition of the messages content */
// rasp -> teensy : 0-127

// Rolling Basis
struct msg_set_target_position
{
    byte command = SET_TARGET_POSITION;
    double target_position_x;
    double target_position_y;
    double target_position_theta;
};

struct msg_set_pid
{
    byte command = SET_PID;
    byte pid_type;
    float kp;
    float ki;
    float kd;
};

// Ignoré si le robot est en mouvement : la Raspberry vérifie dans le statut
// que la nouvelle pose est appliquée
struct msg_reset_pose
{
    byte command = RESET_POSE;
    double x;     // en cm
    double y;     // en cm
    double theta; // en rad
};

// Recul ou avance à vitesse lente jusqu'à toucher une bordure. Statut BLOCKED
// quand les deux roues sont bloquées, STOPPED si rien n'a été touché
struct msg_push_until_blocked
{
    byte command = PUSH_UNTIL_BLOCKED;
    double speed;        // en cm/s, négatif = recul
    double max_distance; // en cm
};

// Messages de test : les moteurs sont coupés à la fin de la durée
struct msg_set_motors_voltage
{
    byte command = SET_MOTORS_VOLTAGE;
    double u_left;   // en V
    double u_right;  // en V
    double duration; // en s
};

struct msg_set_wheels_speed
{
    byte command = SET_WHEELS_SPEED;
    double v_left;   // en cm/s
    double v_right;  // en cm/s
    double duration; // en s
};

// Actuators
struct msg_set_servo_angle
{
    byte command = SET_SERVO_ANGLE;
    byte pin;           // pin to which the servo is connected
    uint16_t angle;     // angle to which the servo should be moved in degrees
    uint16_t max_angle; // max angle reachable by the servo ex : 180, 270
};

struct msg_set_servo_angle_I2C
{
    byte command = SET_SERVO_ANGLE_I2C;
    byte pin;           // pin to which the servo is connected
    uint16_t angle;     // angle to which the servo should be moved in degrees
    uint16_t max_angle; // max angle reachable by the servo ex : 180, 270
};

struct msg_set_servo_angle_detach
{
    byte command = SET_SERVO_ANGLE_DETACH;
    byte pin;           // pin to which the servo is connected
    uint16_t angle;     // angle to which the servo should be moved in degrees
    uint16_t max_angle; // max angle reachable by the servo ex : 180, 270
    int detach_delay;   // delay in milliseconds before detaching the servo
};

struct msg_stepper_step
{
    byte command = STEPPER_STEP;
    int steps;              // total number of steps this motor can take
    bool dir;               // direction of the motor
    int speed;              // speed
    byte pin_dir;           // pin to which the direction pin is connected
    byte pin_step;          // pin to which the step pin is connected
    byte enable_pin_driver; // pin to which the driver pin is connected
};

struct msg_set_stepper_driver_activation_state
{
    byte command = SET_STEPPER_DRIVER_ACTIVATION_STATE;
    byte pin;                 // stepper driver's enable pin
    bool enable_driver_state; // active low so true means the driver is disabled
};

struct msg_attach_switch
{
    byte command = ATTACH_SWITCH;
    byte pin; // pin to which the servo is connected
};

// Common (Rolling Basis + Actuators)
struct msg_reset_teensy
{
    byte command = RESET_TEENSY;
};

// teensy -> rasp : 128-255

// Rolling Basis
struct msg_update_rolling_basis
{
    byte command = UPDATE_ROLLING_BASIS;
    double x;
    double y;
    double theta;
    byte status; // 0 : à l'arrêt, 1 : en mouvement, 2 : bloqué
};

// Mesure envoyée à chaque période pendant un test
struct msg_update_speeds
{
    byte command = UPDATE_SPEEDS;
    uint32_t time_ms;
    double v_left;  // en cm/s
    double v_right; // en cm/s
    double u_left;  // en V
    double u_right; // en V
};

// Actuators
struct msg_switch_state_return
{
    byte command = SWITCH_STATE_RETURN;
    byte pin;   // pin of the switch
    bool state; // switch state
};

// Common (Rolling Basis + Actuators)
struct msg_unknown_msg_type
{
    byte command = UNKNOWN_MSG_TYPE;
    byte type_id; // ID of the unknown message
};
