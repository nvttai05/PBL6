#pragma once
#include <stdint.h>
#include <stddef.h>

namespace Dataset {
struct SerialIrqState {
    bool available=false;
    uint32_t enabledBefore=0,pendingBefore=0,enabledAfter=0,ownedMask=0;
};
SerialIrqState serialIrqState();
bool initializeSerialTransport();
const char* serialTransportName();
int serialTransportError();
int readSerialBytes(uint8_t* bytes, size_t capacity);
int writeSerialBytes(const uint8_t* bytes, size_t length, uint32_t timeoutMs);
bool drainSerialBytes(uint32_t timeoutMs);
}
