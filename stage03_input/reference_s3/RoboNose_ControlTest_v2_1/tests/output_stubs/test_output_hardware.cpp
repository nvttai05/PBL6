#include "Arduino.h"
#include "output_hardware.h"
#include <cassert>

namespace {
int levels[64]{};
uint32_t duty = 999;
uint8_t attachedPin = 0, lastTarget = 255;
bool attachOk = true;
#if ESP_ARDUINO_VERSION_MAJOR >= 3
bool writeOk = true;
#endif
}
void pinMode(uint8_t, int) {}
void digitalWrite(uint8_t pin, int value) { levels[pin] = value; }
#if ESP_ARDUINO_VERSION_MAJOR >= 3
bool ledcAttach(uint8_t pin, uint32_t frequency, uint8_t resolution) {
    attachedPin = pin; assert(frequency == 1000 && resolution == 10); return attachOk;
}
bool ledcWrite(uint8_t pin, uint32_t value) { lastTarget = pin; duty = value; return writeOk; }
bool ledcDetach(uint8_t) { attachedPin = 0; return true; }
#else
double ledcSetup(uint8_t channel, double frequency, uint8_t resolution) {
    assert(channel == 0 && frequency == 1000 && resolution == 10); return attachOk ? frequency : 0;
}
void ledcAttachPin(uint8_t pin, uint8_t channel) { assert(channel == 0); attachedPin = pin; }
void ledcWrite(uint8_t channel, uint32_t value) { lastTarget = channel; duty = value; }
void ledcDetachPin(uint8_t) { attachedPin = 0; }
#endif

int main() {
    assert(initializeOutputHardware());
    assert(attachedPin == 5 && duty == 0 && levels[4] == LOW);
    assert(writePumpDuty(512));
    assert(duty == 512);
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    assert(lastTarget == 5); // 3.x ledcWrite takes PIN, not channel
#else
    assert(lastTarget == 0); // 2.x ledcWrite takes CHANNEL, not pin
#endif
    writeValveOutput(true); assert(levels[4] == HIGH);
    writeValveOutput(false); assert(levels[4] == LOW);
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    writeOk = false;
    assert(!writePumpDuty(600));
    assert(attachedPin == 0 && levels[5] == LOW);
    writeOk = true;
#endif
    attachOk = false;
    assert(!initializeOutputHardware());
    assert(levels[5] == LOW && levels[4] == LOW);
}
