#include "ads1115_reader.h"

bool Ads1115Reader::writeRegister(uint8_t reg, uint16_t value) {
    bus_.beginTransmission(address_);
    bus_.write(reg);
    bus_.write(static_cast<uint8_t>(value >> 8));
    bus_.write(static_cast<uint8_t>(value & 0xFF));
    return bus_.endTransmission(true) == 0;
}

bool Ads1115Reader::readRegister(uint8_t reg, uint16_t& value) {
    bus_.beginTransmission(address_);
    bus_.write(reg);
    if (bus_.endTransmission(false) != 0) return false;
    if (bus_.requestFrom(address_, static_cast<size_t>(2), true) != 2) return false;
    if (bus_.available() < 2) return false;
    const uint8_t high = static_cast<uint8_t>(bus_.read());
    const uint8_t low = static_cast<uint8_t>(bus_.read());
    value = (static_cast<uint16_t>(high) << 8) | low;
    return true;
}

AdsReading Ads1115Reader::read(uint8_t channel) {
    AdsReading out;
    if (channel > 3) { out.error = "bad_channel"; return out; }
    // OS=1, MUX=100..111, PGA=000, MODE=1, DR=100 (128 SPS), COMP_QUE=11.
    const uint16_t wanted = 0x8000 | (static_cast<uint16_t>(4 + channel) << 12)
                            | 0x0100 | 0x0080 | 0x0003;
    if (!writeRegister(1, wanted)) { out.error = "i2c_write_failed"; return out; }
    const uint32_t started = millis();
    uint16_t config = 0;
    while (true) {
        if (!readRegister(1, config)) { out.error = "i2c_config_read_failed"; return out; }
        if ((config & 0x7FE0) != (wanted & 0x7FE0)) {
            out.error = "config_mismatch"; return out;
        }
        if (config & 0x8000) break;
        if (static_cast<uint32_t>(millis() - started) >= 40) {
            out.error = "conversion_timeout"; return out;
        }
        delay(1);
    }
    uint16_t raw = 0;
    if (!readRegister(0, raw)) { out.error = "i2c_conversion_read_failed"; return out; }
    out.count = static_cast<int16_t>(raw);
    out.volts = out.count * LSB_V;
    out.ok = true;
    out.error = "";
    return out;
}
