#include <Arduino.h>
#include <Wire.h>
#include <esp_system.h>
#include <esp_timer.h>
#include <inttypes.h>
#include "config.h"
#include "ads1115_reader.h"
#include "json_line.h"
#include "app.h"
#include "actuators.h"
#include "output_hardware.h"
#include "command_parser.h"
extern "C" {
#include "bme68x.h"
}

#if !defined(CONFIG_IDF_TARGET_ESP32S3)
#error "Select an ESP32-S3 board. This firmware uses two hardware I2C controllers."
#endif

namespace {
TwoWire bmeBus(0);
TwoWire adsBus(1);
Ads1115Reader ads(adsBus, Config::ADS_ADDRESS);
JsonLine json;
ActuatorController outputs({writePumpDuty, writeValveOutput}, Config::CONTROL_TIMEOUT_MS);
struct BmeContext { TwoWire* bus; uint8_t address; } bmeContext{&bmeBus, Config::BME_PREFERRED_ADDRESS};
bme68x_dev bme{};
bme68x_conf bmeConf{};
bme68x_heatr_conf heater{};
bool bmeBusReady = false;
bool adsBusReady = false;
bool bmeReady = false;
uint8_t bmeFailures = 0;
uint64_t bmeRetryAt = 0;
uint64_t nextSampleAt = 0;
uint64_t sequence = 0;
uint64_t skippedIntervals = 0;
char bootId[24]{};
char deviceId[24]{};
char bmeInitError[64] = "not_initialized";
const char* analogNames[] = {"mq135_1", "mq3_1", "tgs2602", "mq3_2"};

uint64_t nowMs() { return static_cast<uint64_t>(esp_timer_get_time()) / 1000; }

void outputState() {
    const auto& state = outputs.state();
    json.integer("pump_pwm_pct", state.pumpPct);
    json.integer("pump_pwm_duty", state.pumpDuty);
    json.boolean("valve_energized", state.valveEnergized);
    json.text("valve_air_path_commanded", state.valveEnergized ? "SAMPLE" : "FILTERED_AIR");
    json.boolean("failsafe_active", state.failsafe);
    json.boolean("control_ready", state.ready);
    json.integer("control_revision", state.revision);
    json.integer("lease_remaining_ms", outputs.leaseRemaining(nowMs()));
}

void common(const char* type) {
    json.begin(type);
    json.text("schema", Config::SCHEMA);
    json.text("boot_id", bootId);
}

void event(const char* code, const char* detail) {
    common("event");
    json.integer("uptime_ms", nowMs());
    json.text("code", code);
    json.text("detail", detail);
    outputState();
    json.send();
}

BME68X_INTF_RET_TYPE bmeRead(uint8_t reg, uint8_t* data, uint32_t length, void* ptr) {
    auto* ctx = static_cast<BmeContext*>(ptr);
    if (!data || length == 0 || length > 128) return -1;
    ctx->bus->beginTransmission(ctx->address);
    ctx->bus->write(reg);
    if (ctx->bus->endTransmission(false) != 0) return -1;
    if (ctx->bus->requestFrom(ctx->address, static_cast<size_t>(length), true) != length) return -1;
    for (uint32_t i = 0; i < length; ++i) {
        if (!ctx->bus->available()) return -1;
        data[i] = static_cast<uint8_t>(ctx->bus->read());
    }
    return 0;
}

BME68X_INTF_RET_TYPE bmeWrite(uint8_t reg, const uint8_t* data, uint32_t length, void* ptr) {
    auto* ctx = static_cast<BmeContext*>(ptr);
    if (!data || length == 0 || length > 127) return -1;
    ctx->bus->beginTransmission(ctx->address);
    ctx->bus->write(reg);
    if (ctx->bus->write(data, length) != length) return -1;
    return ctx->bus->endTransmission(true) == 0 ? 0 : -1;
}

void bmeDelay(uint32_t us, void*) {
    if (us >= 1000) delay(us / 1000);
    if (us % 1000) delayMicroseconds(us % 1000);
}

bool probe(TwoWire& bus, uint8_t address) {
    bus.beginTransmission(address);
    return bus.endTransmission(true) == 0;
}

bool initializeBme() {
    if (!bmeBusReady) { snprintf(bmeInitError, sizeof(bmeInitError), "bus_init_failed"); return false; }
    const uint8_t alternate = Config::BME_PREFERRED_ADDRESS == 0x77 ? 0x76 : 0x77;
    if (probe(bmeBus, Config::BME_PREFERRED_ADDRESS)) bmeContext.address = Config::BME_PREFERRED_ADDRESS;
    else if (probe(bmeBus, alternate)) bmeContext.address = alternate;
    else { snprintf(bmeInitError, sizeof(bmeInitError), "no_device_at_0x77_or_0x76"); return false; }
    bme = {};
    bme.intf = BME68X_I2C_INTF;
    bme.read = bmeRead;
    bme.write = bmeWrite;
    bme.delay_us = bmeDelay;
    bme.intf_ptr = &bmeContext;
    bme.amb_temp = 25;
    int8_t rslt = bme68x_init(&bme);
    if (rslt != BME68X_OK) {
        snprintf(bmeInitError, sizeof(bmeInitError), "bosch_init_%d", rslt); return false;
    }
    bmeConf = {};
    bmeConf.filter = BME68X_FILTER_OFF;
    bmeConf.odr = BME68X_ODR_NONE;
    bmeConf.os_hum = BME68X_OS_2X;
    bmeConf.os_pres = BME68X_OS_4X;
    bmeConf.os_temp = BME68X_OS_2X;
    rslt = bme68x_set_conf(&bmeConf, &bme);
    if (rslt != BME68X_OK) {
        snprintf(bmeInitError, sizeof(bmeInitError), "bosch_config_%d", rslt); return false;
    }
    heater = {};
    heater.enable = BME68X_ENABLE;
    heater.heatr_temp = Config::BME_HEATER_TEMP_C;
    heater.heatr_dur = Config::BME_HEATER_DURATION_MS;
    rslt = bme68x_set_heatr_conf(BME68X_FORCED_MODE, &heater, &bme);
    if (rslt != BME68X_OK) {
        snprintf(bmeInitError, sizeof(bmeInitError), "bosch_heater_%d", rslt); return false;
    }
    bmeFailures = 0;
    bmeInitError[0] = 0;
    return true;
}

void hello() {
    common("hello");
    json.text("firmware_version", Config::FIRMWARE_VERSION);
    json.text("device_id", deviceId);
    json.text("hardware_revision", Config::HARDWARE);
    json.integer("uptime_ms", nowMs());
    json.integer("sample_interval_ms", Config::SAMPLE_INTERVAL_MS);
    json.integer("bme_sda", Config::BME_SDA); json.integer("bme_scl", Config::BME_SCL);
    json.integer("ads_sda", Config::ADS_SDA); json.integer("ads_scl", Config::ADS_SCL);
    json.integer("i2c_hz", Config::I2C_HZ);
    json.integer("ads_address", Config::ADS_ADDRESS);
    json.number("ads_fsr_v", 6.144); json.number("ads_lsb_v", Ads1115Reader::LSB_V, 7);
    json.integer("ads_data_rate_sps", 128); json.number("divider_factor", 1.0, 1);
    json.boolean("bme_initialized", bmeReady);
    json.integer("bme_address", bmeContext.address);
    if (bmeReady) json.integer("bme_variant_id", bme.variant_id);
    else json.nullValue("bme_variant_id");
    json.integer("bme_heater_temp_c", Config::BME_HEATER_TEMP_C);
    json.integer("bme_heater_duration_ms", Config::BME_HEATER_DURATION_MS);
    json.text("bme_mode", "forced");
    json.text("bme_init_error", bmeInitError);
    json.text("channel_map", "A0=mq135_1,A1=mq3_1,A2=tgs2602,A3=mq3_2");
    json.text("valve_off_air_path", "FILTERED_AIR");
    json.text("valve_on_air_path", "SAMPLE");
    json.text("valve_air_path_source", "user_confirmed_plumbing_2026-11-06");
    json.boolean("actuator_control", true);
    json.integer("control_protocol", 1);
    json.integer("pump_pin", Config::PUMP_PIN);
    json.integer("valve_pin", Config::VALVE_PIN);
    json.integer("pump_pwm_hz", Config::PUMP_PWM_HZ);
    json.integer("pump_pwm_bits", 10);
    json.boolean("pump_active_high", Config::PUMP_ACTIVE_HIGH);
    json.boolean("valve_active_high", Config::VALVE_ACTIVE_HIGH);
    json.integer("control_timeout_ms", Config::CONTROL_TIMEOUT_MS);
    json.text("output_feedback", "commanded_only_no_rpm_flow_or_valve_feedback");
    outputState();
    json.send();
}

struct BmeReading {
    bool ok = false;
    bool hasStatus = false;
    bme68x_data data{};
    char error[64] = "not_read";
};

BmeReading readBme() {
    BmeReading out;
    if (!bmeReady) { snprintf(out.error, sizeof(out.error), "%s", bmeInitError); return out; }
    int8_t rslt = bme68x_set_op_mode(BME68X_FORCED_MODE, &bme);
    if (rslt != BME68X_OK) {
        snprintf(out.error, sizeof(out.error), "bosch_trigger_%d", rslt); return out;
    }
    const uint32_t us = bme68x_get_meas_dur(BME68X_FORCED_MODE, &bmeConf, &bme)
                        + static_cast<uint32_t>(heater.heatr_dur) * 1000;
    delay((us + 999) / 1000 + 2);
    uint8_t fields = 0;
    rslt = bme68x_get_data(BME68X_FORCED_MODE, &out.data, &fields, &bme);
    if (rslt != BME68X_OK) {
        snprintf(out.error, sizeof(out.error), "bosch_read_%d", rslt); return out;
    }
    if (!fields) { snprintf(out.error, sizeof(out.error), "no_new_data"); return out; }
    out.hasStatus = true;
    if (!(out.data.status & BME68X_NEW_DATA_MSK)) {
        snprintf(out.error, sizeof(out.error), "no_new_data"); return out;
    }
    out.ok = true;
    out.error[0] = 0;
    return out;
}

void sample(uint64_t scheduledAt) {
    const uint64_t started = nowMs();
    const uint32_t revisionAtStart = outputs.state().revision;
    AdsReading a[4];
    for (uint8_t channel = 0; channel < 4; ++channel) {
        if (adsBusReady) a[channel] = ads.read(channel);
        else a[channel].error = "bus_init_failed";
    }
    BmeReading b = readBme();
    const uint64_t ended = nowMs();
    common("sample");
    json.integer("seq", sequence++);
    json.integer("device_cycle_start_ms", started);
    json.integer("device_cycle_end_ms", ended);
    json.integer("acquisition_duration_ms", ended - started);
    json.integer("schedule_lag_ms", started - scheduledAt);
    json.integer("skipped_intervals_total", skippedIntervals);
    for (uint8_t channel = 0; channel < 4; ++channel) {
        char key[40];
        snprintf(key, sizeof(key), "%s_count", analogNames[channel]);
        if (a[channel].ok) json.integer(key, a[channel].count); else json.nullValue(key);
        snprintf(key, sizeof(key), "%s_voltage_v", analogNames[channel]);
        if (a[channel].ok) json.number(key, a[channel].volts); else json.nullValue(key);
        snprintf(key, sizeof(key), "ads_a%u_error", channel); json.text(key, a[channel].error);
    }
    if (b.ok) {
        json.number("temperature_c", b.data.temperature, 3);
        json.number("humidity_pct", b.data.humidity, 3);
        json.number("pressure_hpa", b.data.pressure / 100.0, 3);
        json.number("bme688_gas_ohm", b.data.gas_resistance, 3);
        bme.amb_temp = static_cast<int8_t>(b.data.temperature);
    } else {
        json.nullValue("temperature_c"); json.nullValue("humidity_pct");
        json.nullValue("pressure_hpa"); json.nullValue("bme688_gas_ohm");
    }
    if (b.hasStatus) {
        json.boolean("bme_new_data", b.data.status & BME68X_NEW_DATA_MSK);
        json.boolean("gas_valid", b.data.status & BME68X_GASM_VALID_MSK);
        json.boolean("heater_stable", b.data.status & BME68X_HEAT_STAB_MSK);
        json.integer("bme_status_raw", b.data.status);
    } else {
        json.nullValue("bme_new_data"); json.nullValue("gas_valid");
        json.nullValue("heater_stable"); json.nullValue("bme_status_raw");
    }
    json.text("bme_error", b.error);
    outputState();
    json.integer("control_revision_start", revisionAtStart);
    json.boolean("control_changed_during_scan", revisionAtStart != outputs.state().revision);
    json.send();
    if (b.ok) bmeFailures = 0;
    else if (bmeReady && ++bmeFailures >= 3) {
        bmeReady = false;
        snprintf(bmeInitError, sizeof(bmeInitError), "%s", b.error);
        bmeRetryAt = nowMs() + 5000;
        event("bme_retry_scheduled", b.error);
    }
}

void execute(char* input) {
    const Command command = parseCommand(input);
    const char* error = command.error;
    if (command.kind == CommandKind::Info) hello();
    else if (command.kind == CommandKind::Ping) outputs.heartbeat(nowMs());
    else if (command.kind == CommandKind::Help) event("help", "INFO;PING;PUMP 0..100;VALVE ON/OFF;ALL OFF");
    else if (command.kind == CommandKind::Pump) error = outputs.setPump(command.value, nowMs());
    else if (command.kind == CommandKind::Valve) error = outputs.setValve(command.value, nowMs());
    else if (command.kind == CommandKind::AllOff && !outputs.allOff(nowMs())) error = "off_pwm_write_failed";
    common("ack");
    json.integer("request_id", command.requestId);
    json.text("command", commandName(command.kind));
    json.boolean("ok", error[0] == 0);
    json.text("error", error);
    json.integer("device_ms", nowMs());
    outputState();
    json.send();
}

void commands() {
    static char input[80];
    static size_t used = 0;
    static bool overflowing = false;
    // Bound the work per loop even if the host floods the serial port.
    for (int n = 0; n < 128 && Serial.available(); ++n) {
        const char c = static_cast<char>(Serial.read());
        if (c == '\r') continue;
        if (c == '\n') {
            if (overflowing) event("bad_command", "command_too_long");
            else {
                input[used] = 0;
                if (used) execute(input);
            }
            used = 0; overflowing = false;
        } else if (used < sizeof(input) - 1 && !overflowing) input[used++] = c;
        else overflowing = true;
    }
}
} // namespace

void robonoseSetup() {
    // Initialize commanded OFF levels before sensor initialization or USB waits.
    outputs.begin(initializeOutputHardware(), nowMs());
    Serial.begin(Config::SERIAL_BAUD);
    snprintf(bootId, sizeof(bootId), "%08" PRIx32 "%08" PRIx32, esp_random(), esp_random());
    snprintf(deviceId, sizeof(deviceId), "%012" PRIx64, ESP.getEfuseMac());
    bmeBusReady = bmeBus.begin(Config::BME_SDA, Config::BME_SCL, Config::I2C_HZ);
    adsBusReady = adsBus.begin(Config::ADS_SDA, Config::ADS_SCL, Config::I2C_HZ);
    bmeBus.setTimeOut(Config::I2C_TIMEOUT_MS);
    adsBus.setTimeOut(Config::I2C_TIMEOUT_MS);
    bmeReady = initializeBme();
    bmeRetryAt = nowMs() + 5000;
    hello();
    nextSampleAt = nowMs();
}

void robonoseLoop() {
    if (outputs.tick(nowMs())) event("watchdog_all_off", "heartbeat_timeout");
    commands();
    if (nowMs() >= nextSampleAt) {
        sample(nextSampleAt);
        nextSampleAt += Config::SAMPLE_INTERVAL_MS;
        const uint64_t ended = nowMs();
        if (ended >= nextSampleAt) {
            const uint64_t skipped = (ended - nextSampleAt) / Config::SAMPLE_INTERVAL_MS + 1;
            sequence += skipped; skippedIntervals += skipped;
            nextSampleAt += skipped * Config::SAMPLE_INTERVAL_MS;
        }
        if (!bmeReady && nowMs() >= bmeRetryAt) {
            bmeReady = initializeBme();
            bmeRetryAt = nowMs() + 5000;
            event(bmeReady ? "bme_reinitialized" : "bme_init_failed", bmeInitError);
            if (bmeReady) hello();
        }
    }
    delay(1);
}
