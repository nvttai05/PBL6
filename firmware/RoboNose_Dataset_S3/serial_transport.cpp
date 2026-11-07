#include <Arduino.h>
#include "config.h"
#include "serial_transport.h"
#include "usb_irq_policy.h"
#if ARDUINO_USB_CDC_ON_BOOT && ARDUINO_USB_MODE == 1
#include <driver/usb_serial_jtag.h>
#include <freertos/FreeRTOS.h>
#include <hal/usb_serial_jtag_ll.h>
#include <esp_private/periph_ctrl.h>
#define DATASET_IDF_USB 1
#else
#define DATASET_IDF_USB 0
#endif

namespace Dataset {
namespace {
bool initialized=false;
int initializationError=0;
SerialIrqState interruptState;
#if DATASET_IDF_USB
static_assert(USB_STREAM_OWNED_IRQS==(USB_SERIAL_JTAG_INTR_SERIAL_IN_EMPTY|USB_SERIAL_JTAG_INTR_SERIAL_OUT_RECV_PKT),
              "USB IRQ policy must match the installed ESP32-S3 SDK");
struct UsbRegisters {
    uint32_t enabled() { return usb_serial_jtag_ll_get_intr_ena_status(); }
    uint32_t pending() { return usb_serial_jtag_ll_get_intraw_mask(); }
    void disable(uint32_t mask) { usb_serial_jtag_ll_disable_intr_mask(mask); }
    void clear(uint32_t mask) { usb_serial_jtag_ll_clr_intsts_mask(mask); }
};
#endif
}
SerialIrqState serialIrqState() { return interruptState; }
const char* serialTransportName() {
#if DATASET_IDF_USB
    return "idf_usb_serial_jtag";
#elif ARDUINO_USB_CDC_ON_BOOT
    return "arduino_usb_otg_cdc";
#else
    return "arduino_uart";
#endif
}
bool initializeSerialTransport() {
    initialized=false; initializationError=0; interruptState=SerialIrqState{};
#if DATASET_IDF_USB
    // Own the native USB peripheral through IDF, not Arduino HWCDC's
    // disconnected FIFO-replacement path (which can silently truncate JSON).
    // Do not call Serial.begin(): two ISR owners must never share this port.
    if(usb_serial_jtag_is_driver_installed()) {
        initializationError=ESP_ERR_INVALID_STATE;
        return false;
    }
    PERIPH_RCC_ATOMIC() { usb_serial_jtag_ll_enable_bus_clock(true); }
    UsbRegisters registers;
    UsbIrqSnapshot before=prepareUsbInterrupts(registers,USB_SERIAL_JTAG_LL_INTR_MASK);
    interruptState={true,before.enabled,before.pending,0,USB_STREAM_OWNED_IRQS};
    usb_serial_jtag_driver_config_t settings{};
    settings.tx_buffer_size=Config::SERIAL_TX_BUFFER_BYTES;
    settings.rx_buffer_size=Config::SERIAL_RX_BUFFER_BYTES;
    initializationError=usb_serial_jtag_driver_install(&settings);
    initialized=initializationError==ESP_OK;
    registers.disable(USB_SERIAL_JTAG_LL_INTR_MASK & ~USB_STREAM_OWNED_IRQS);
    interruptState.enabledAfter=registers.enabled();
#else
    Serial.setRxBufferSize(Config::SERIAL_RX_BUFFER_BYTES);
    Serial.begin(Config::SERIAL_BAUD);
#if ARDUINO_USB_CDC_ON_BOOT
    Serial.setTxTimeoutMs(20);
#endif
    initialized=true;
#endif
    return initialized;
}
int serialTransportError() { return initializationError; }
int readSerialBytes(uint8_t* bytes,size_t capacity) {
    if(!initialized) return -1;
#if DATASET_IDF_USB
    return usb_serial_jtag_read_bytes(bytes,capacity,0);
#else
    size_t read=0;
    while(read<capacity&&Serial.available()>0) {
        int value=Serial.read(); if(value<0) break;
        bytes[read++]=static_cast<uint8_t>(value);
    }
    return static_cast<int>(read);
#endif
}
int writeSerialBytes(const uint8_t* bytes,size_t length,uint32_t timeoutMs) {
    if(!initialized) return -1;
#if DATASET_IDF_USB
    return usb_serial_jtag_write_bytes(bytes,length,pdMS_TO_TICKS(timeoutMs));
#else
    (void)timeoutMs;
    int capacity=Serial.availableForWrite();
    if(capacity<=0) return 0;
    if(length>static_cast<size_t>(capacity)) length=capacity;
    return static_cast<int>(Serial.write(bytes,length));
#endif
}
bool drainSerialBytes(uint32_t timeoutMs) {
    if(!initialized) return false;
#if DATASET_IDF_USB
    return usb_serial_jtag_wait_tx_done(pdMS_TO_TICKS(timeoutMs))==ESP_OK;
#else
    (void)timeoutMs;
    return true; // UART/OTG write acceptance, not host receipt/physical OFF.
#endif
}
}
