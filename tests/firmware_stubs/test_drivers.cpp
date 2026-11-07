#include <cassert>
#include <cmath>
#include <cstring>
#include "ads1115_reader.h"
#include "output_hardware.h"
#include "sensor_policy.h"
uint32_t fake_ms=0;
int levels[64]{}; bool attachOk=true,writeOk=true; uint32_t duty=999; uint8_t target=0;
void pinMode(uint8_t,int) {}
void digitalWrite(uint8_t pin,int value) { levels[pin]=value; }
bool ledcAttach(uint8_t pin,uint32_t hz,uint8_t bits) { assert(pin==5&&hz==1000&&bits==10); return attachOk; }
bool ledcWrite(uint8_t pin,uint32_t value) { target=pin; duty=value; return writeOk; }
bool ledcDetach(uint8_t) { return true; }
int main() {
    assert(initializeOutputHardware()&&duty==0&&levels[4]==LOW);
    assert(writePumpDuty(818)&&target==5&&duty==818);
    writeValveOutput(true); assert(levels[4]==HIGH); writeValveOutput(false);
    writeOk=false; assert(!writePumpDuty(800)&&levels[5]==LOW); writeOk=true;
    attachOk=false; assert(!initializeOutputHardware()&&levels[5]==LOW&&levels[4]==LOW);
    TwoWire wire; Ads1115Reader reader(wire,0x48);
    for(unsigned channel=0;channel<4;++channel) {
        AdsReading result=reader.read(channel);
        assert(result.ok&&result.count==wire.analog[channel]);
        assert(std::fabs(result.volts-result.count*.0001875)<1e-10);
        assert(((wire.configs.back()>>12)&7)==channel+4);
        assert((wire.configs.back()&0xfff)==0x183);
    }
    wire.wrongAfter=true; auto result=reader.read(0);
    assert(!result.ok&&strstr(result.error,"config_mismatch_after"));
    wire.wrongAfter=false; wire.failWrite=true; result=reader.read(0);
    assert(!result.ok&&strstr(result.error,"bus=1")&&strstr(result.error,"addr=0x48")&&strstr(result.error,"Wire=2"));
    wire.failWrite=false; wire.busy=true; result=reader.read(0);
    assert(!result.ok&&strstr(result.error,"conversion_timeout"));
    assert(!SensorPolicy::fresh(0,0xff)&&!SensorPolicy::fresh(1,0x30)&&SensorPolicy::fresh(1,0x80));
}
