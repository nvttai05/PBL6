#pragma once
#include <stdint.h>
constexpr int OUTPUT = 1, HIGH = 1, LOW = 0;
void pinMode(uint8_t pin, int mode);
void digitalWrite(uint8_t pin, int value);
#if ESP_ARDUINO_VERSION_MAJOR >= 3
bool ledcAttach(uint8_t pin, uint32_t frequency, uint8_t resolution);
bool ledcWrite(uint8_t pin, uint32_t duty);
bool ledcDetach(uint8_t pin);
#else
double ledcSetup(uint8_t channel, double frequency, uint8_t resolution);
void ledcAttachPin(uint8_t pin, uint8_t channel);
void ledcWrite(uint8_t channel, uint32_t duty);
void ledcDetachPin(uint8_t pin);
#endif
