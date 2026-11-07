#include <cassert>
#include <cmath>
#include <cstring>
#include "ads1115_reader.h"
uint32_t fake_ms = 0;

int main() {
    TwoWire wire;
    Ads1115Reader reader(wire, 0x48);
    for (unsigned i = 0; i < 4; ++i) {
        AdsReading r = reader.read(i);
        assert(r.ok && r.count == wire.analog[i]);
        assert(std::fabs(r.volts - wire.analog[i] * .0001875f) < .000001f);
        assert(((wire.configs.back() >> 12) & 7) == i + 4);
        assert((wire.configs.back() & 0x0FFF) == 0x0183); // PGA=0, MODE=1, DR=128
    }
    wire.failWrite = true;
    AdsReading r = reader.read(0);
    assert(!r.ok && !strcmp(r.error, "i2c_write_failed"));
    wire.failWrite = false; wire.shortRead = true;
    r = reader.read(0);
    assert(!r.ok && !strcmp(r.error, "i2c_config_read_failed"));
    wire.shortRead = false; wire.busy = true;
    r = reader.read(2);
    assert(!r.ok && !strcmp(r.error, "conversion_timeout"));
    wire.busy = false; wire.wrongMux = true;
    r = reader.read(2);
    assert(!r.ok && !strcmp(r.error, "config_mismatch"));
    assert(!reader.read(4).ok);
}
