#pragma once
#include <stdint.h>

namespace Config {
constexpr uint8_t BME_SDA=8, BME_SCL=9, ADS_SDA=10, ADS_SCL=11;
constexpr uint8_t ADS_ADDRESS=0x48, BME_PREFERRED_ADDRESS=0x77;
constexpr uint32_t I2C_HZ=100000, SAMPLE_INTERVAL_MS=1000, SERIAL_BAUD=115200;
constexpr uint16_t I2C_TIMEOUT_MS=50;
constexpr uint16_t BME_HEATER_TEMP_C=300, BME_HEATER_DURATION_MS=100;
constexpr uint8_t PUMP_PIN=5, VALVE_PIN=4, PUMP_PWM_CHANNEL=0;
constexpr bool PUMP_ACTIVE_HIGH=true, VALVE_ACTIVE_HIGH=true;
constexpr uint32_t PUMP_PWM_HZ=1000, CONTROL_TIMEOUT_MS=15000;
constexpr const char* FIRMWARE_VERSION="3.0.0";
constexpr const char* FIRMWARE_REVISION="usb_irq_handoff.v3";
constexpr const char* SCHEMA="robonose.dataset.v1";
constexpr const char* PROTOCOL="robonose.usb.v1";
constexpr const char* PROFILE="s3_bringup_300_100_t2h2p4.v1";
constexpr const char* CHANNEL_MAP="A0=tgs2602,A1=mq3_1,A2=mq135_2,A3=mq3_2";
constexpr const char* ANALOG_NAMES[]={"tgs2602","mq3_1","mq135_2","mq3_2"};
constexpr unsigned MAX_FRAME=8192, MAX_COMMAND=192;
constexpr unsigned SERIAL_TX_BUFFER_BYTES=2*MAX_FRAME, SERIAL_RX_BUFFER_BYTES=1024;
static_assert(SERIAL_TX_BUFFER_BYTES>=MAX_FRAME,"USB TX buffer must hold a complete frame");
}
