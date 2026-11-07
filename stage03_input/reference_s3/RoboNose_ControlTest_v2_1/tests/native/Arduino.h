#pragma once
#include <stdint.h>
#include <stddef.h>
extern uint32_t fake_ms;
inline uint32_t millis() { return fake_ms; }
inline void delay(uint32_t ms) { fake_ms += ms; }
