#pragma once
#include <stdint.h>
bool initializeOutputHardware();
bool writePumpDuty(uint16_t logicalDuty);
void writeValveOutput(bool energized);
