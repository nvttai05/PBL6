#include "sensors.h"
#include "config.h"
#include "sensor_policy.h"
#include <esp_timer.h>
#include <string.h>

namespace {
TwoWire bmeBus(0), adsBus(1);
Ads1115Reader ads(adsBus,Config::ADS_ADDRESS);
struct BmeContext { uint8_t address=0x77; int wireCode=0; const char* stage="none"; } context;
bme68x_dev bme{}; bme68x_conf conf{}; bme68x_heatr_conf heater{};
SensorInfo info;
uint64_t nowMs() { return esp_timer_get_time()/1000; }
BME68X_INTF_RET_TYPE readBme(uint8_t reg,uint8_t* data,uint32_t size,void*) {
    context.stage="read_pointer";
    bmeBus.beginTransmission(context.address); bmeBus.write(reg);
    context.wireCode=bmeBus.endTransmission(false); if(context.wireCode) return -1;
    context.stage="read_data";
    if(bmeBus.requestFrom(context.address,static_cast<size_t>(size),true)!=size) { context.wireCode=-2; return -1; }
    for(uint32_t i=0;i<size;++i) { if(!bmeBus.available()) { context.wireCode=-3; return -1; } data[i]=bmeBus.read(); }
    return 0;
}
BME68X_INTF_RET_TYPE writeBme(uint8_t reg,const uint8_t* data,uint32_t size,void*) {
    context.stage="write"; bmeBus.beginTransmission(context.address); bmeBus.write(reg);
    if(bmeBus.write(data,size)!=size) { context.wireCode=-1; return -1; }
    context.wireCode=bmeBus.endTransmission(true); return context.wireCode?-1:0;
}
void delayBme(uint32_t us,void*) { if(us>=1000) delay(us/1000); if(us%1000) delayMicroseconds(us%1000); }
bool probe(uint8_t address) { bmeBus.beginTransmission(address); return bmeBus.endTransmission(true)==0; }
void diagnostic(char* out,size_t size,const char* stage,int code) {
    snprintf(out,size,"BME bus=0 addr=0x%02x stage=%s/%s Bosch=%d Wire=%d",context.address,stage,context.stage,code,context.wireCode);
}
}
SensorInfo initializeSensors() {
    bool bmeBusReady=bmeBus.begin(Config::BME_SDA,Config::BME_SCL,Config::I2C_HZ);
    info.adsReady=adsBus.begin(Config::ADS_SDA,Config::ADS_SCL,Config::I2C_HZ);
    bmeBus.setTimeOut(Config::I2C_TIMEOUT_MS); adsBus.setTimeOut(Config::I2C_TIMEOUT_MS);
    if(!bmeBusReady) { strcpy(info.error,"BME bus=0 begin_failed"); info.initialized=true; return info; }
    if(probe(0x77)) context.address=0x77; else if(probe(0x76)) context.address=0x76;
    else { strcpy(info.error,"BME bus=0 probe 0x77/0x76 failed"); info.initialized=true; return info; }
    info.address=context.address;
    bme.intf=BME68X_I2C_INTF; bme.read=readBme; bme.write=writeBme; bme.delay_us=delayBme; bme.intf_ptr=&context; bme.amb_temp=25;
    int8_t result=bme68x_init(&bme);
    if(result) { diagnostic(info.error,sizeof(info.error),"init",result); info.initialized=true; return info; }
    conf.filter=BME68X_FILTER_OFF; conf.odr=BME68X_ODR_NONE;
    conf.os_temp=BME68X_OS_2X; conf.os_hum=BME68X_OS_2X; conf.os_pres=BME68X_OS_4X;
    result=bme68x_set_conf(&conf,&bme);
    if(!result) { heater.enable=BME68X_ENABLE; heater.heatr_temp=300; heater.heatr_dur=100; result=bme68x_set_heatr_conf(BME68X_FORCED_MODE,&heater,&bme); }
    bme68x_conf applied{};
    if(!result) result=bme68x_get_conf(&applied,&bme);
    uint8_t registers[3]={};
    if(!result) result=bme68x_get_regs(BME68X_REG_RES_HEAT0,&registers[0],1,&bme);
    if(!result) result=bme68x_get_regs(BME68X_REG_GAS_WAIT0,&registers[1],1,&bme);
    if(!result) result=bme68x_get_regs(BME68X_REG_IDAC_HEAT0,&registers[2],1,&bme);
    info.resHeat=registers[0]; info.gasWait=registers[1]; info.idac=registers[2];
    info.gasWaitMs=(info.gasWait&63)*(1u<<(2*(info.gasWait>>6)));
    info.osT=applied.os_temp?1u<<(applied.os_temp-1):0;
    info.osH=applied.os_hum?1u<<(applied.os_hum-1):0;
    info.osP=applied.os_pres?1u<<(applied.os_pres-1):0;
    info.readbackOk=!result&&applied.os_temp==conf.os_temp&&applied.os_hum==conf.os_hum&&applied.os_pres==conf.os_pres&&applied.filter==conf.filter&&info.gasWaitMs==100;
    info.bmeReady=info.readbackOk; info.variant=bme.variant_id; info.chip=bme.chip_id;
    if(!info.bmeReady) diagnostic(info.error,sizeof(info.error),"config_readback",result?result:-99); else info.error[0]=0;
    info.initialized=true; return info;
}
ScanResult readSensors(const ScanJob& job) {
    ScanResult out; out.job=job; out.started=nowMs();
    for(uint8_t channel=0;channel<4;++channel) {
        if(info.adsReady) out.analog[channel]=ads.read(channel);
        else { out.analog[channel].started=nowMs(); strcpy(out.analog[channel].error,"ADS bus=1 begin_failed"); }
    }
    out.bmeStarted=nowMs();
    if(info.bmeReady) {
        int8_t result=bme68x_set_op_mode(BME68X_FORCED_MODE,&bme);
        if(!result) {
            uint32_t duration=bme68x_get_meas_dur(BME68X_FORCED_MODE,&conf,&bme)+info.gasWaitMs*1000;
            delay((duration+999)/1000+2); uint8_t fields=0;
            result=bme68x_get_data(BME68X_FORCED_MODE,&out.bme,&fields,&bme);
            out.bmeStatus=!result&&fields;
            out.bmeFresh=!result&&SensorPolicy::fresh(fields,out.bme.status);
            if(out.bmeFresh) { out.bmeError[0]=0; bme.amb_temp=out.bme.temperature; }
            else if(!result) strcpy(out.bmeError,"no_new_data");
        }
        if(result) diagnostic(out.bmeError,sizeof(out.bmeError),"forced_read",result);
    } else strncpy(out.bmeError,info.error,sizeof(out.bmeError)-1);
    out.bmeDuration=nowMs()-out.bmeStarted; out.ended=nowMs(); return out;
}
