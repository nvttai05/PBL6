#include "ads1115_reader.h"
#include <esp_timer.h>
static uint64_t clockMs() { return esp_timer_get_time()/1000; }
void Ads1115Reader::error(AdsReading& out,const char* stage,int code) {
    snprintf(out.error,sizeof(out.error),"ADS bus=1 addr=0x%02x stage=%s Wire=%d",address_,stage,code);
}
bool Ads1115Reader::writeRegister(uint8_t reg,uint16_t value,AdsReading& out) {
    bus_.beginTransmission(address_);
    if(bus_.write(reg)!=1||bus_.write(static_cast<uint8_t>(value>>8))!=1||bus_.write(static_cast<uint8_t>(value))!=1) {
        error(out,"config_buffer",-1); return false;
    }
    uint8_t result=bus_.endTransmission(true);
    if(result) { error(out,"config_write",result); return false; } return true;
}
bool Ads1115Reader::readRegister(uint8_t reg,uint16_t& value,AdsReading& out,const char* stage) {
    bus_.beginTransmission(address_); bus_.write(reg); uint8_t result=bus_.endTransmission(false);
    if(result) { error(out,stage,result); return false; }
    size_t got=bus_.requestFrom(address_,static_cast<size_t>(2),true);
    if(got!=2||bus_.available()<2) { error(out,stage,-2); return false; }
    uint8_t high=bus_.read(),low=bus_.read(); value=(static_cast<uint16_t>(high)<<8)|low; return true;
}
AdsReading Ads1115Reader::read(uint8_t channel) {
    AdsReading out; out.started=clockMs();
    auto finish=[&]() { out.duration=clockMs()-out.started; return out; };
    if(channel>3) { error(out,"channel",-3); return finish(); }
    uint16_t wanted=0x8000|((4+channel)<<12)|0x0183, config=0, raw=0;
    if(!writeRegister(1,wanted,out)) return finish();
    while(true) {
        if(!readRegister(1,config,out,"config_before")) return finish();
        if((config&0x7fff)!=(wanted&0x7fff)) { error(out,"config_mismatch_before",config); return finish(); }
        if(config&0x8000) break;
        if(clockMs()-out.started>=100) { error(out,"conversion_timeout",-4); return finish(); }
        delay(1);
    }
    if(!readRegister(0,raw,out,"conversion")) return finish();
    if(!readRegister(1,config,out,"config_after")) return finish();
    if((config&0x7fff)!=(wanted&0x7fff)) { error(out,"config_mismatch_after",config); return finish(); }
    out.count=static_cast<int16_t>(raw); out.volts=out.count*LSB_V; out.ok=true; out.error[0]=0; return finish();
}
