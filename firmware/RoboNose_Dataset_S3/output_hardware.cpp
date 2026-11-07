#include <Arduino.h>
#include <esp_arduino_version.h>
#include "config.h"
#include "output_hardware.h"

namespace {
bool pwmAttached = false;
uint16_t electrical(uint16_t logical) { return Config::PUMP_ACTIVE_HIGH ? logical : 1023 - logical; }
void inactivePumpGpio() {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    if (pwmAttached) ledcDetach(Config::PUMP_PIN);
#else
    if (pwmAttached) ledcDetachPin(Config::PUMP_PIN);
#endif
    pwmAttached = false;
    pinMode(Config::PUMP_PIN, OUTPUT);
    digitalWrite(Config::PUMP_PIN, Config::PUMP_ACTIVE_HIGH ? LOW : HIGH);
}
}

void writeValveOutput(bool energized) {
    digitalWrite(Config::VALVE_PIN, energized == Config::VALVE_ACTIVE_HIGH ? HIGH : LOW);
}

bool initializeOutputHardware() {
    // Set inactive levels before attaching PWM. External pulls are needed to
    // establish the desired level before firmware starts executing at boot.
    digitalWrite(Config::PUMP_PIN, Config::PUMP_ACTIVE_HIGH ? LOW : HIGH);
    pinMode(Config::PUMP_PIN, OUTPUT);
    digitalWrite(Config::VALVE_PIN, Config::VALVE_ACTIVE_HIGH ? LOW : HIGH);
    pinMode(Config::VALVE_PIN, OUTPUT);
    writeValveOutput(false);
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    pwmAttached = ledcAttach(Config::PUMP_PIN, Config::PUMP_PWM_HZ, 10);
#else
    pwmAttached = ledcSetup(Config::PUMP_PWM_CHANNEL, Config::PUMP_PWM_HZ, 10) > 0;
    if (pwmAttached) ledcAttachPin(Config::PUMP_PIN, Config::PUMP_PWM_CHANNEL);
#endif
    if (!pwmAttached) { inactivePumpGpio(); return false; }
    return writePumpDuty(0);
}

bool writePumpDuty(uint16_t logicalDuty) {
    if (!pwmAttached) { inactivePumpGpio(); return logicalDuty == 0; }
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    if (!ledcWrite(Config::PUMP_PIN, electrical(logicalDuty))) { inactivePumpGpio(); return false; }
#else
    ledcWrite(Config::PUMP_PWM_CHANNEL, electrical(logicalDuty));
#endif
    return true;
}
