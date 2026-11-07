#include <Arduino.h>
#include <esp_timer.h>
#include <esp_system.h>
#include <atomic>
#include <initializer_list>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>
#include "config.h"
#include "trial_engine.h"
#include "time_policy.h"
#include "sensors.h"
#include "output_hardware.h"
#include "json_frame.h"
#include "runtime.h"
#include "serial_transport.h"
#include "framed_tx.h"
#if !defined(CONFIG_IDF_TARGET_ESP32S3)
#error "This dataset sketch requires ESP32-S3; generic compile is not board identification."
#endif

namespace {
using namespace Dataset;
uint64_t nowMs() { return esp_timer_get_time()/1000; }
struct TxFrame { size_t length=0; char bytes[Config::MAX_FRAME]; };
// Control/Arduino loop has an 8 KiB stack on the provisional board profile.
// Keep its complete frame staging buffer in static storage, not on that stack.
TxFrame stagingFrame;
QueueHandle_t jobs=nullptr, results=nullptr, txQueue=nullptr;
struct ReceivedLine { char bytes[Config::MAX_COMMAND]{}; bool overflow=false; };
QueueHandle_t commandsQueue=nullptr;
ReceivedLine urgentLine;
std::atomic<bool> urgentReady{false}, rxFault{false}, txBusy{false};
portMUX_TYPE sharedMux=portMUX_INITIALIZER_UNLOCKED;
SensorInfo sensorInfo;
uint64_t txProgress=0;
std::atomic<bool> txFault{false};
bool tasksReady=false;
bool serialReady=false;
uint64_t nextScan=0, issued=0, outstandingSince=0, lastFreshScan=0;
bool outstanding=false, preflight=false;
unsigned failedScans=0;
char deviceId[24]{};
void transitionEvent(const Transition& event,void*);
Engine engine({writePumpDuty,writeValveOutput},transitionEvent);
JsonFrame json;

void common(const char* type,const char* sessionOverride=nullptr) {
    json.begin(type); json.text("protocol",Config::PROTOCOL); json.text("schema",Config::SCHEMA);
    json.text("mode","HARDWARE"); json.text("boot_id",engine.boot); json.text("session_id",sessionOverride?sessionOverride:engine.session);
    json.integer("device_ms",nowMs());
}
void stateFields(const Context& state) {
    json.text("phase",phaseName(state.phase)); json.integer("context_epoch",state.epoch);
    json.integer("segment_id",state.segment); json.integer("trial_index",state.trialIndex);
    if(state.trial[0]) json.text("trial_id",state.trial); else json.nullValue("trial_id");
    json.text("trial_status",state.status); json.integer("phase_started_ms",state.started);
    if(state.deadline) json.integer("deadline_ms",state.deadline); else json.nullValue("deadline_ms");
    json.integer("pump_pwm_pct",state.pwm); json.boolean("valve_energized",state.valve);
    json.text("air_path_commanded",state.valve?"SAMPLE":"FILTERED_AIR");
    if(state.faultReason[0]) json.text("fault_reason",state.faultReason); else json.nullValue("fault_reason");
}
void send() {
    const String& text=json.finish();
    if(text.length()>=Config::MAX_FRAME||!txQueue) { txFault=true; return; }
    stagingFrame.length=text.length(); memcpy(stagingFrame.bytes,text.c_str(),stagingFrame.length);
    if(xQueueSend(txQueue,&stagingFrame,0)!=pdTRUE) txFault=true;
}
void transitionEvent(const Transition& change,void*) {
    common("event"); json.text("event","phase_change");
    json.text("previous_phase",phaseName(change.before.phase));
    if(change.before.trial[0]) json.text("previous_trial_id",change.before.trial); else json.nullValue("previous_trial_id");
    json.integer("effective_ms",change.effective); json.integer("processed_ms",change.processed);
    json.integer("barrier_seq",change.barrier); stateFields(change.after); send();
}
SensorInfo infoSnapshot() {
    portENTER_CRITICAL(&sharedMux); SensorInfo copy=sensorInfo; portEXIT_CRITICAL(&sharedMux); return copy;
}
void hello() {
    SensorInfo info=infoSnapshot(); common("hello"); json.text("firmware_version",Config::FIRMWARE_VERSION);
    json.text("firmware_revision",Config::FIRMWARE_REVISION);
    json.text("serial_transport",serialTransportName()); json.boolean("serial_ready",serialReady);
    json.integer("serial_init_error",serialTransportError());
    json.integer("serial_tx_buffer_requested_bytes",Config::SERIAL_TX_BUFFER_BYTES);
    json.integer("serial_rx_buffer_requested_bytes",Config::SERIAL_RX_BUFFER_BYTES);
    SerialIrqState irq=serialIrqState();
    json.boolean("serial_irq_diagnostics_available",irq.available);
    json.integer("serial_irq_enabled_before",irq.enabledBefore);
    json.integer("serial_irq_pending_before",irq.pendingBefore);
    json.integer("serial_irq_enabled_after_init",irq.enabledAfter);
    json.integer("serial_irq_owned_mask",irq.ownedMask);
    if(!engine.latched&&(engine.state.phase==Phase::OFF||engine.state.phase==Phase::CLOSED)) {
        snprintf(engine.beginTicket,sizeof(engine.beginTicket),"%08lx%08lx",static_cast<unsigned long>(esp_random()),static_cast<unsigned long>(esp_random()));
    }
    json.text("begin_ticket",engine.beginTicket);
    json.text("firmware_kind","robonose_dataset_s3"); json.text("device_id",deviceId);
    json.integer("reset_reason",esp_reset_reason()); json.text("channel_map",Config::CHANNEL_MAP);
    json.number("ads_fsr_v",6.144); json.number("ads_lsb_v",Ads1115Reader::LSB_V);
    json.number("divider_factor",1); json.integer("ads_data_rate_sps",128);
    json.text("ads_mode","single_shot_single_ended"); json.number("ads_vdd_requested_v",5);
    json.integer("ads_address",Config::ADS_ADDRESS); json.integer("ads_sda",Config::ADS_SDA); json.integer("ads_scl",Config::ADS_SCL);
    json.integer("bme_sda",Config::BME_SDA); json.integer("bme_scl",Config::BME_SCL); json.integer("bme_address",info.address);
    json.integer("i2c_hz",Config::I2C_HZ); json.integer("i2c_timeout_ms",Config::I2C_TIMEOUT_MS);
    json.text("profile_id",Config::PROFILE); json.integer("heater_requested_c",300); json.integer("heater_requested_ms",100);
    json.integer("os_t_requested",2); json.integer("os_h_requested",2); json.integer("os_p_requested",4);
    json.integer("os_t_applied",info.osT); json.integer("os_h_applied",info.osH); json.integer("os_p_applied",info.osP);
    json.integer("heater_res_heat_readback",info.resHeat); json.integer("heater_gas_wait_readback",info.gasWait);
    json.integer("heater_idac_readback",info.idac); json.integer("heater_applied_ms",info.gasWaitMs);
    json.integer("bme_chip_id",info.chip); json.integer("bme_variant_id",info.variant);
    json.boolean("profile_readback_ok",info.readbackOk); json.nullValue("production_profile");
    json.boolean("sensors_initialized",info.initialized); json.boolean("sensors_ready",preflight);
    json.text("sensor_init_error",info.error); json.boolean("output_ready",engine.ready&&tasksReady);
    json.integer("pump_pin",5); json.integer("valve_pin",4); json.integer("pump_pwm_hz",1000); json.integer("pump_pwm_bits",10);
    json.text("valve_off_air_path","FILTERED_AIR"); json.text("valve_on_air_path","SAMPLE");
    json.integer("sample_interval_ms",1000); json.integer("lease_ms",15000);
    json.boolean("fault_latched",engine.latched); stateFields(engine.state); send();
}
void ack(const Reply& reply) {
    common("ack"); json.integer("request_id",reply.id); json.boolean("accepted",reply.accepted);
    json.text("reason",reply.reason); json.integer("applied_ms",reply.applied); json.integer("barrier_seq",reply.barrier);
    stateFields(reply.context); send();
}
void sample(const ScanResult& scan) {
    common("sample",scan.job.session);
    // Job session/context are immutable even when BEGIN/NEXT/OFF happened during I2C.
    stateFields(scan.job.context);
    json.integer("seq",scan.job.seq); json.number("mono_s",scan.started/1000.0);
    json.number("cycle_end_mono_s",scan.ended/1000.0);
    json.number("schedule_lag_s",(scan.started-scan.job.scheduled)/1000.0);
    json.integer("skipped_cycles",scan.job.skipped);
    json.number("phase_elapsed_s",(scan.started-scan.job.context.started)/1000.0);
    json.boolean("context_straddled",scan.job.context.epoch!=engine.state.epoch);
    json.text("profile_id",Config::PROFILE); json.text("quality_flags","HARDWARE;COMMAND_STATE_ONLY");
    for(unsigned channel=0;channel<4;++channel) {
        const AdsReading& reading=scan.analog[channel]; const char* id=Config::ANALOG_NAMES[channel]; char key[64];
        const bool limit=reading.count==32767||reading.count==-32768;
        snprintf(key,sizeof(key),"%s_adc_count",id); if(reading.ok) json.integer(key,reading.count); else json.nullValue(key);
        snprintf(key,sizeof(key),"%s_voltage_v",id); if(reading.ok) json.number(key,reading.volts); else json.nullValue(key);
        snprintf(key,sizeof(key),"%s_read_started_mono_s",id); json.number(key,reading.started/1000.0);
        snprintf(key,sizeof(key),"%s_read_duration_s",id); json.number(key,reading.duration/1000.0);
        snprintf(key,sizeof(key),"%s_status",id); json.text(key,reading.ok?(limit?"ADC_LIMIT":reading.count<0?"NEGATIVE":"OK"):"ERROR");
        snprintf(key,sizeof(key),"%s_error",id); if(reading.ok) json.nullValue(key); else json.text(key,reading.error);
        snprintf(key,sizeof(key),"%s_fresh",id); json.boolean(key,reading.ok);
        snprintf(key,sizeof(key),"%s_valid",id); json.boolean(key,reading.ok&&!limit);
    }
    if(scan.bmeFresh) {
        json.number("gas_resistance_ohm",scan.bme.gas_resistance); json.number("temperature_c",scan.bme.temperature);
        json.number("humidity_pct",scan.bme.humidity); json.number("pressure_hpa",scan.bme.pressure/100.0);
    } else for(const char* key:{"gas_resistance_ohm","temperature_c","humidity_pct","pressure_hpa"}) json.nullValue(key);
    json.boolean("new_data",scan.bmeFresh);
    json.boolean("gas_valid",scan.bmeStatus&&(scan.bme.status&BME68X_GASM_VALID_MSK));
    json.boolean("heater_stable",scan.bmeStatus&&(scan.bme.status&BME68X_HEAT_STAB_MSK));
    if(scan.bmeStatus) { json.integer("bme_status_bits",scan.bme.status); json.integer("bme_meas_index",scan.bme.meas_index); }
    else { json.nullValue("bme_status_bits"); json.nullValue("bme_meas_index"); }
    json.number("bme688_read_started_mono_s",scan.bmeStarted/1000.0); json.number("bme688_read_duration_s",scan.bmeDuration/1000.0);
    json.text("bme688_status",scan.bmeFresh?"OK":!strcmp(scan.bmeError,"no_new_data")?"STALE":"ERROR");
    if(scan.bmeFresh) json.nullValue("bme688_error"); else json.text("bme688_error",scan.bmeError);
    json.boolean("bme688_fresh",scan.bmeFresh); json.boolean("bme688_valid",scan.bmeFresh); send();
}
void sensorTask(void*) {
    SensorInfo info=initializeSensors(); portENTER_CRITICAL(&sharedMux); sensorInfo=info; portEXIT_CRITICAL(&sharedMux);
    ScanJob job;
    while(true) if(xQueueReceive(jobs,&job,portMAX_DELAY)==pdTRUE) {
        ScanResult result=readSensors(job);
        if(xQueueSend(results,&result,0)!=pdTRUE) { portENTER_CRITICAL(&sharedMux); strcpy(sensorInfo.error,"sensor_result_queue_full"); portEXIT_CRITICAL(&sharedMux); }
    }
}
void transmitPause() { vTaskDelay(pdMS_TO_TICKS(1)); }
void transmitTask(void*) {
    TxFrame frame;
    bool needsDelimiter=false;
    while(true) if(xQueueReceive(txQueue,&frame,portMAX_DELAY)==pdTRUE) {
        txBusy=true;
        if(needsDelimiter) {
            const uint8_t delimiter='\n';
            if(!transmitFrame(&delimiter,1,{writeSerialBytes,drainSerialBytes,nowMs,transmitPause})) {
                txFault=true; txBusy=false; continue;
            }
            needsDelimiter=false;
        }
        bool complete=transmitFrame(reinterpret_cast<const uint8_t*>(frame.bytes),frame.length,
                                   {writeSerialBytes,drainSerialBytes,nowMs,transmitPause});
        portENTER_CRITICAL(&sharedMux); txProgress=nowMs(); portEXIT_CRITICAL(&sharedMux);
        txBusy=false;
        // Report incomplete writes to the output owner; never turn a pump on here.
        if(!complete) { txFault=true; needsDelimiter=true; }
    }
}
void receiveTask(void*) {
    ReceivedLine line; unsigned used=0;
    while(true) {
        uint8_t bytes[256]; int count=readSerialBytes(bytes,sizeof(bytes));
        if(count<0) rxFault=true;
        for(int position=0;position<count;++position) {
            char ch=static_cast<char>(bytes[position]); if(ch=='\r') continue;
            if(ch=='\n') {
                line.bytes[used]=0;
                if(used||line.overflow) {
                    Request request=line.overflow?Request{}:parseRequest(line.bytes);
                    if(request.valid&&(!strcmp(request.verb,"OFF")||!strcmp(request.verb,"FAULT"))) {
                        portENTER_CRITICAL(&sharedMux); urgentLine=line; portEXIT_CRITICAL(&sharedMux);
                        urgentReady=true;
                    } else if(xQueueSend(commandsQueue,&line,0)!=pdTRUE) rxFault=true;
                }
                used=0; line.overflow=false;
            } else if(static_cast<unsigned char>(ch)<32&&ch!='\t') line.overflow=true;
            else if(used<sizeof(line.bytes)-1&&!line.overflow) line.bytes[used++]=ch;
            else line.overflow=true;
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
}
void executeLine(const ReceivedLine& line) {
    if(line.overflow) { common("parser_event"); json.text("reason","command_too_long_or_invalid_control_byte"); send(); }
    else if(!strcmp(line.bytes,"HELLO")) hello();
    else ack(engine.command(parseRequest(line.bytes),nowMs(),preflight&&nowMs()-lastFreshScan<3000));
}
void commands() {
    if(urgentReady.exchange(false)) {
        ReceivedLine copy; portENTER_CRITICAL(&sharedMux); copy=urgentLine; portEXIT_CRITICAL(&sharedMux); executeLine(copy);
    }
    ReceivedLine line;
    for(unsigned count=0;count<8&&commandsQueue&&xQueueReceive(commandsQueue,&line,0)==pdTRUE;++count) executeLine(line);
}
}
void datasetSetup() {
    char boot[33]; snprintf(boot,sizeof(boot),"%08lx%08lx",static_cast<unsigned long>(esp_random()),static_cast<unsigned long>(esp_random()));
    engine.initialize(initializeOutputHardware(),boot); // Inactive before USB/sensors/task creation.
    snprintf(deviceId,sizeof(deviceId),"%012llx",static_cast<unsigned long long>(ESP.getEfuseMac()));
    serialReady=initializeSerialTransport();
    jobs=xQueueCreate(1,sizeof(ScanJob)); results=xQueueCreate(1,sizeof(ScanResult)); txQueue=xQueueCreate(4,sizeof(TxFrame));
    commandsQueue=xQueueCreate(8,sizeof(ReceivedLine));
    tasksReady=serialReady&&jobs&&results&&txQueue&&commandsQueue;
    if(tasksReady) {
        tasksReady=xTaskCreate(sensorTask,"dataset-i2c",8192,nullptr,1,nullptr)==pdPASS;
        tasksReady=tasksReady&&xTaskCreate(transmitTask,"dataset-tx",12288,nullptr,1,nullptr)==pdPASS;
        tasksReady=tasksReady&&xTaskCreate(receiveTask,"dataset-rx",4096,nullptr,1,nullptr)==pdPASS;
    }
    if(!tasksReady) { engine.ready=false; engine.stop(nowMs(),true,"task_init_failed"); }
    txProgress=nowMs(); nextScan=nowMs(); hello();
}
void datasetLoop() {
    uint64_t now=nowMs(); engine.tick(now); commands();
    uint64_t progress; portENTER_CRITICAL(&sharedMux); progress=txProgress; portEXIT_CRITICAL(&sharedMux);
    // Commands can enqueue multiple frames and yield to TX. Read time AFTER
    // the progress snapshot, then use guarded age checks for task timestamps.
    now=nowMs();
    if(engine.state.pwm&&(txFault||rxFault||((txBusy||uxQueueMessagesWaiting(txQueue)>0)&&elapsedMs(now,progress)>2000))) engine.stop(now,true,"usb_task_stalled_or_queue_full");
    if(!engine.state.pwm) { txFault=false; rxFault=false; }
    if(outstanding&&elapsedMs(now,outstandingSince)>2000&&engine.state.pwm) engine.stop(now,true,"sensor_task_stalled");
    ScanResult result;
    if(results&&xQueueReceive(results,&result,0)==pdTRUE) {
        outstanding=false; preflight=result.bmeFresh;
        for(const auto& analog:result.analog) preflight=preflight&&analog.ok&&analog.count!=32767&&analog.count!=-32768;
        if(preflight) { lastFreshScan=now; failedScans=0; } else ++failedScans;
        sample(result);
        if(failedScans>=3&&engine.state.pwm) engine.stop(now,true,"required_sensor_failure");
    }
    SensorInfo info=infoSnapshot();
    if(tasksReady&&info.initialized&&!outstanding&&now>=nextScan) {
        ScanJob job; job.context=engine.state; strcpy(job.session,engine.session); job.seq=++issued; job.scheduled=nextScan;
        job.skipped=(now-nextScan)/1000;
        engine.scanBarrier=issued; nextScan+=1000;
        if(now>=nextScan) nextScan+=(now-nextScan)/1000*1000+1000;
        if(xQueueSend(jobs,&job,0)!=pdTRUE) engine.stop(now,true,"sensor_job_queue_full");
        else { outstanding=true; outstandingSince=now; }
    }
    delay(1);
}
