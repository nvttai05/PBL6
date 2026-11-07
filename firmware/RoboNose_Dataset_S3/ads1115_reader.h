#pragma once
#include <Arduino.h>
#include <Wire.h>
struct AdsReading {
    bool ok=false; int16_t count=0; double volts=0;
    uint64_t started=0, duration=0;
    char error[112]="not_read";
};
class Ads1115Reader {
public:
    Ads1115Reader(TwoWire& bus,uint8_t address):bus_(bus),address_(address) {}
    AdsReading read(uint8_t channel);
    static constexpr double LSB_V=.0001875;
private:
    bool writeRegister(uint8_t reg,uint16_t value,AdsReading& out);
    bool readRegister(uint8_t reg,uint16_t& value,AdsReading& out,const char* stage);
    void error(AdsReading& out,const char* stage,int code);
    TwoWire& bus_; uint8_t address_;
};
