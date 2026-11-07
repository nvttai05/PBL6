#pragma once
#include "Arduino.h"
#include <vector>
#include <array>

class TwoWire {
public:
    bool failWrite = false, shortRead = false, busy = false, wrongMux = false;
    std::vector<uint16_t> configs;
    std::array<int16_t, 4> analog = {{1234, -1, 10000, 20000}};
    void beginTransmission(uint8_t) { tx.clear(); }
    size_t write(uint8_t v) { tx.push_back(v); return 1; }
    uint8_t endTransmission(bool) {
        if (failWrite) return 2;
        if (tx.size() == 1) reg = tx[0];
        if (tx.size() == 3) {
            config = (static_cast<uint16_t>(tx[1]) << 8) | tx[2];
            configs.push_back(config); polls = 0;
        }
        return 0;
    }
    size_t requestFrom(uint8_t, size_t, bool) {
        if (shortRead) { rx.clear(); return 0; }
        uint16_t value;
        if (reg == 1) {
            value = config & 0x7FFF;
            if (!busy && polls++ >= 1) value |= 0x8000;
            if (wrongMux) value ^= 0x1000;
        } else {
            unsigned channel = ((config >> 12) & 7) - 4;
            value = static_cast<uint16_t>(analog.at(channel));
        }
        rx = {static_cast<uint8_t>(value >> 8), static_cast<uint8_t>(value & 0xff)};
        return rx.size();
    }
    int available() { return static_cast<int>(rx.size()); }
    int read() { const uint8_t v = rx.front(); rx.erase(rx.begin()); return v; }
private:
    std::vector<uint8_t> tx, rx;
    uint8_t reg = 0;
    uint16_t config = 0;
    unsigned polls = 0;
};
