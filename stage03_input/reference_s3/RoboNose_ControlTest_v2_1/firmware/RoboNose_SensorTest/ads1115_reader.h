#pragma once
#include <Arduino.h>
#include <Wire.h>

struct AdsReading {
    bool ok = false;
    int16_t count = 0;
    float volts = 0.0f;
    const char* error = "not_read";
};

// Single owner, single-shot, AINx relative to GND. PGA bits 000: +/-6.144 V.
class Ads1115Reader {
public:
    Ads1115Reader(TwoWire& bus, uint8_t address) : bus_(bus), address_(address) {}
    AdsReading read(uint8_t channel);
    static constexpr float LSB_V = 0.0001875f;
private:
    bool writeRegister(uint8_t reg, uint16_t value);
    bool readRegister(uint8_t reg, uint16_t& value);
    TwoWire& bus_;
    uint8_t address_;
};
