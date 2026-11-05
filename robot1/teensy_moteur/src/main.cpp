// Externe libraries used: Arduino, TimerOne, ATOMIC
#include <Arduino.h>      // Arduino framework
#include <TimerOne.h>     // Timer interrupt library
#include <util/atomic.h>  // Atomic block library

// Custom libraries used: RollingBasis, Com
#include <rolling_basis.h>  // Rolling Basis object to manage the motors and robot position

// Configuration file (contains all the constants and pinout), it is just a
// main.cpp header file
#include <config.h>

// 1. Instanciate the Rolling Basis object
// a. Define the PID controllers
PID linear_position_pid(KP_LINEAR_POSITION, 0, 0, -V_MAX, V_MAX, TS);
PID angular_position_pid(KP_ANGULAR_POSITION, 0, 0, -W_MAX, W_MAX, TS);

// PI de vitesse : un par roue, leur sortie est une tension
// Rolling_Basis en garde une copie, ces objets servent de valeurs de départ
PID left_speed_pid(KP_SPEED_LEFT, KI_SPEED_LEFT, 0, -U_MAX, U_MAX, TS);
PID right_speed_pid(KP_SPEED_RIGHT, KI_SPEED_RIGHT, 0, -U_MAX, U_MAX, TS);

// b. Instanciate the Rolling Basis object
Rolling_Basis* rolling_basis_ptr = new Rolling_Basis(ENCODER_RESOLUTION,
                                                     ENTRAXE,
                                                     WHEEL_DIAMETER,
                                                     linear_position_pid,
                                                     angular_position_pid,
                                                     left_speed_pid,
                                                     right_speed_pid);

// 2. Instanciate the Communication object
Com* com;

// 3. Define all com callback functions
// a. define globals variables to keep in memory callback functions updated
Point target_position(START_X, START_Y, START_THETA);

// dernière mesure de test, écrite par le timer et envoyée par loop()
msg_update_speeds speeds_msg;
volatile bool speeds_ready = false;

// b. define the callback functions
void set_target_position(byte* msg, byte size) {
    msg_set_target_position* target_position_msg =
        (msg_set_target_position*)msg;

    // Update position
    target_position.x = target_position_msg->target_position_x;
    target_position.y = target_position_msg->target_position_y;
    target_position.theta = target_position_msg->target_position_theta;
}

void set_pid(byte* msg, byte size) {
    msg_set_pid* pid_msg = (msg_set_pid*)msg;
    PID* pid = nullptr;
    bool is_valid_pid = true;
    // pid pointe vers la copie gardée par Rolling_Basis, celle qui tourne
    switch (pid_msg->pid_type) {
        case LINEAR_POSITION_PID_ID:
            pid = &rolling_basis_ptr->linear_distance_pid;
            break;
        case ANGULAR_POSITION_PID_ID:
            pid = &rolling_basis_ptr->angular_distance_pid;
            break;
        case LEFT_SPEED_PID_ID:
            pid = &rolling_basis_ptr->left_speed_pid;
            break;
        case RIGHT_SPEED_PID_ID:
            pid = &rolling_basis_ptr->right_speed_pid;
            break;
        default:
            is_valid_pid = false;
            break;
    }
    if (is_valid_pid) {
        // le timer ne doit pas utiliser le PID pendant le changement de gains
        noInterrupts();
        pid->updateParameters(pid_msg->kp, pid_msg->ki, pid_msg->kd);
        interrupts();
    }
}

// Test en boucle ouverte : une tension par moteur, pendant une durée limitée
void set_motors_voltage(byte* msg, byte size) {
    msg_set_motors_voltage* voltage_msg = (msg_set_motors_voltage*)msg;

    // la durée d'abord, sinon le timer verrait 0 et couperait l'essai
    rolling_basis_ptr->test_periods_left = voltage_msg->duration / TS;
    rolling_basis_ptr->set_open_loop(voltage_msg->u_left, voltage_msg->u_right);
}

// Test des PI : une vitesse par roue, pendant une durée limitée
void set_wheels_speed(byte* msg, byte size) {
    msg_set_wheels_speed* speed_msg = (msg_set_wheels_speed*)msg;

    // la durée d'abord, sinon le timer verrait 0 et couperait l'essai
    rolling_basis_ptr->test_periods_left = speed_msg->duration / TS;
    rolling_basis_ptr->set_speed_targets(speed_msg->v_left, speed_msg->v_right);
}

void set_odometrie(byte* msg, byte size) {
    msg_set_odometrie* odometrie = (msg_set_odometrie*)msg;

    rolling_basis_ptr->X = odometrie->x;
    rolling_basis_ptr->Y = odometrie->y;
    rolling_basis_ptr->THETA = odometrie->theta;

    // Update target position: avoid the usage of old stored target point
    target_position.x = odometrie->x;
    target_position.y = odometrie->y;
    target_position.theta = odometrie->theta;
}

void reset_teensy(byte* msg, byte size) {
    // TODO: reset the teensy, à tester !
    void (*reboot)(void) = 0;
    reboot();
}

// c. assign the callback functions to the right message id
void (*callback_functions[256])(byte* msg, byte size);

void initialize_callback_functions() {
    callback_functions[SET_TARGET_POSITION] = &set_target_position;
    callback_functions[SET_PID] = &set_pid;
    callback_functions[SET_ODOMETRIE] = &set_odometrie;
    callback_functions[SET_MOTORS_VOLTAGE] = &set_motors_voltage;
    callback_functions[SET_WHEELS_SPEED] = &set_wheels_speed;
    callback_functions[RESET_TEENSY] = &reset_teensy;
}

// 4. Define the timer interrupt handle function (this function will be called
// every 5ms, and which manage the robot position and speed: asservissement)
void handle() {
    rolling_basis_ptr->odometrie_handle();
    rolling_basis_ptr->handle(target_position, com);

    // pendant un test, on prépare la mesure que loop() enverra
    if (rolling_basis_ptr->test_periods_left > 0) {
        speeds_msg.time_ms = millis();
        speeds_msg.v_left = rolling_basis_ptr->left_motor->speed;
        speeds_msg.v_right = rolling_basis_ptr->right_motor->speed;
        speeds_msg.u_left = rolling_basis_ptr->left_motor->voltage;
        speeds_msg.u_right = rolling_basis_ptr->right_motor->voltage;
        speeds_ready = true;
    }
}

void setup() {
    com = new Com(&Serial, BAUDRATE);

    // Change pwm frequency
    analogWriteFrequency(R_PWM, PWM_FREQUENCY);
    analogWriteFrequency(L_PWM, PWM_FREQUENCY);

    // change pwm resolution
    analogWriteResolution(PWM_RESOLUTION);

    // Init Rolling Basis
    rolling_basis_ptr->define_right_motor(R_ENCA, R_ENCB, R_PWM, R_DIR, PWM_MAX,
                                          U_MAX, TS);
    rolling_basis_ptr->define_left_motor(L_ENCA, L_ENCB, L_PWM, L_DIR, PWM_MAX,
                                         U_MAX, TS);
    rolling_basis_ptr->init_motors();

    rolling_basis_ptr->init_rolling_basis(START_X, START_Y, START_THETA);

    rolling_basis_ptr->vbat = VBAT_DEFAULT;

    // Init motors handle timer
    Timer1.initialize(ASSERVISSEMENT_PERIOD);
    Timer1.attachInterrupt(handle);

    // Initialize callback functions
    initialize_callback_functions();
}

uint_fast32_t counter = 0;
void loop() {
    // Handle the communication
    com->handle_callback(callback_functions);

    // Send the last test measure: the copy keeps the timer from changing it
    if (speeds_ready) {
        msg_update_speeds speeds_copy;
        ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
            speeds_copy = speeds_msg;
            speeds_ready = false;
        }
        com->send_msg((byte*)&speeds_copy, sizeof(msg_update_speeds));
    }

    // Send rolling basis state
    if (counter++ > 4096)  // 4096 = 2^12
    {
        msg_update_rolling_basis rolling_basis_msg;
        // Rolling Basis position
        rolling_basis_msg.x = rolling_basis_ptr->X;
        rolling_basis_msg.y = rolling_basis_ptr->Y;
        rolling_basis_msg.theta = rolling_basis_ptr->THETA;

        com->send_msg((byte*)&rolling_basis_msg,
                      sizeof(msg_update_rolling_basis));
        counter = 0;
    }
}
