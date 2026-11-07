// RoboNose v2.1: MQ + TGS2602 (A2) + BME688, pump GPIO5, valve GPIO4.
// Keep ALL files in this sketch folder. Main implementation: sensor_test.cpp.
// After upload, use pc/monitor.py for live charts and output controls.
#include <Arduino.h>
#include "app.h"

void setup() {
    robonoseSetup();
}

void loop() {
    robonoseLoop();
}
