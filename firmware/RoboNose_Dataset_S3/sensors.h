#pragma once
#include "ads1115_reader.h"
#include "trial_engine.h"
extern "C" {
#include "bme68x.h"
}
struct SensorInfo {
    bool initialized=false, bmeReady=false, adsReady=false, readbackOk=false;
    uint8_t address=0x77, variant=0, chip=0, resHeat=0, gasWait=0, idac=0;
    unsigned gasWaitMs=0, osT=0, osH=0, osP=0;
    char error[112]="initializing";
};
struct ScanJob { Dataset::Context context; char session[37]{}; uint64_t seq=0,scheduled=0,skipped=0; };
struct ScanResult {
    ScanJob job; uint64_t started=0, ended=0, bmeStarted=0, bmeDuration=0;
    AdsReading analog[4]; bme68x_data bme{};
    bool bmeFresh=false, bmeStatus=false; char bmeError[112]="not_read";
};
SensorInfo initializeSensors();
ScanResult readSensors(const ScanJob& job);
