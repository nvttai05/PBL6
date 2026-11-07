#pragma once
#include <stdint.h>

namespace Config {
constexpr uint8_t BME_SDA = 8;
constexpr uint8_t BME_SCL = 9;
constexpr uint8_t ADS_SDA = 10;
constexpr uint8_t ADS_SCL = 11;
constexpr uint8_t ADS_ADDRESS = 0x48;
constexpr uint8_t BME_PREFERRED_ADDRESS = 0x77;
constexpr uint32_t I2C_HZ = 100000;
constexpr uint16_t I2C_TIMEOUT_MS = 50;
constexpr uint32_t SAMPLE_INTERVAL_MS = 1000;
constexpr uint16_t BME_HEATER_TEMP_C = 300;
constexpr uint16_t BME_HEATER_DURATION_MS = 100;
constexpr uint32_t SERIAL_BAUD = 115200;
constexpr uint8_t PUMP_PIN = 5;
constexpr uint8_t VALVE_PIN = 4;
constexpr bool PUMP_ACTIVE_HIGH = true;
constexpr bool VALVE_ACTIVE_HIGH = true;
constexpr uint32_t PUMP_PWM_HZ = 1000;
constexpr uint8_t PUMP_PWM_CHANNEL = 0; // Arduino-ESP32 2.x only
constexpr uint32_t CONTROL_TIMEOUT_MS = 15000;
constexpr const char* FIRMWARE_VERSION = "2.1.0";
constexpr const char* SCHEMA = "robonose.control_test.v2.1";
constexpr const char* HARDWARE = "esp32s3_5v_tgs2602_a2_no_divider";
static_assert(SAMPLE_INTERVAL_MS >= 250, "Sample interval must be >= 250 ms");
static_assert(BME_HEATER_TEMP_C <= 400, "Check BME heater configuration");
} // namespace Config
