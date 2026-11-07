#include <cassert>
#include <cstdio>
#include <cstring>
#include "config.h"
#include "serial_transport.h"
#include "driver/usb_serial_jtag.h"
#include "hal/usb_serial_jtag_ll.h"

bool installed=false;
esp_err_t installResult=ESP_OK,drainResult=ESP_OK;
usb_serial_jtag_driver_config_t actual{};
int writeResult=0,readResult=0;
uint32_t fake_usb_irq_enabled=0x20c,fake_usb_irq_pending=0x20c;
bool usb_serial_jtag_is_driver_installed() { return installed; }
esp_err_t usb_serial_jtag_driver_install(usb_serial_jtag_driver_config_t* config) {
    assert(fake_usb_irq_enabled==0);
    assert((fake_usb_irq_pending&USB_SERIAL_JTAG_INTR_BUS_RESET)==0);
    actual=*config; installed=installResult==ESP_OK;
    if(installed) fake_usb_irq_enabled|=USB_SERIAL_JTAG_INTR_SERIAL_OUT_RECV_PKT;
    return installResult;
}
int usb_serial_jtag_read_bytes(void*,uint32_t,TickType_t wait) { assert(wait==0); return readResult; }
int usb_serial_jtag_write_bytes(const void*,size_t,TickType_t wait) { assert(wait<=20); return writeResult; }
esp_err_t usb_serial_jtag_wait_tx_done(TickType_t wait) { assert(wait<=20); return drainResult; }
int main() {
    using namespace Dataset;
    uint8_t bytes[64]{};
    installed=true; assert(!initializeSerialTransport());
    assert(serialTransportError()==ESP_ERR_INVALID_STATE);
    assert(fake_usb_irq_enabled==0x20c); // Never disturb an existing owner.
    installed=false; installResult=ESP_FAIL; assert(!initializeSerialTransport());
    assert(writeSerialBytes(bytes,sizeof(bytes),20)==-1);
    fake_usb_irq_enabled=0x20c; fake_usb_irq_pending=0x20c;
    installResult=ESP_OK; assert(initializeSerialTransport());
    assert(!strcmp(serialTransportName(),"idf_usb_serial_jtag"));
    assert(actual.tx_buffer_size>=Config::MAX_FRAME&&actual.rx_buffer_size==1024);
    auto irq=serialIrqState();
    assert(irq.enabledBefore==0x20c&&irq.pendingBefore==0x20c);
    assert(irq.enabledAfter==4&&irq.ownedMask==12&&fake_usb_irq_pending==12);
    writeResult=7; assert(writeSerialBytes(bytes,sizeof(bytes),20)==7);
    writeResult=0; assert(writeSerialBytes(bytes,sizeof(bytes),20)==0);
    writeResult=-1; assert(writeSerialBytes(bytes,sizeof(bytes),20)==-1);
    readResult=3; assert(readSerialBytes(bytes,sizeof(bytes))==3);
    drainResult=ESP_ERR_TIMEOUT; assert(!drainSerialBytes(20));
    drainResult=ESP_OK; assert(drainSerialBytes(20));
    puts("IDF USB transport ownership, buffers and exact write counts passed");
}
