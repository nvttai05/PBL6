#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
extern uint32_t fake_ms;
inline uint32_t millis() { return fake_ms; }
inline void delay(uint32_t ms) { fake_ms+=ms; }
#define HIGH 1
#define LOW 0
#define OUTPUT 1
void pinMode(uint8_t,int);
void digitalWrite(uint8_t,int);
bool ledcAttach(uint8_t,uint32_t,uint8_t);
bool ledcWrite(uint8_t,uint32_t);
bool ledcDetach(uint8_t);
