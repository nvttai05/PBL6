#pragma once
#include <stdint.h>
#define USB_SERIAL_JTAG_LL_INTR_MASK 0x7ffffu
constexpr uint32_t USB_SERIAL_JTAG_INTR_SERIAL_OUT_RECV_PKT=1u<<2;
constexpr uint32_t USB_SERIAL_JTAG_INTR_SERIAL_IN_EMPTY=1u<<3;
constexpr uint32_t USB_SERIAL_JTAG_INTR_BUS_RESET=1u<<9;
extern uint32_t fake_usb_irq_enabled,fake_usb_irq_pending;
inline void usb_serial_jtag_ll_enable_bus_clock(bool) {}
inline uint32_t usb_serial_jtag_ll_get_intr_ena_status() { return fake_usb_irq_enabled; }
inline uint32_t usb_serial_jtag_ll_get_intraw_mask() { return fake_usb_irq_pending; }
inline void usb_serial_jtag_ll_disable_intr_mask(uint32_t mask) { fake_usb_irq_enabled&=~mask; }
inline void usb_serial_jtag_ll_clr_intsts_mask(uint32_t mask) { fake_usb_irq_pending&=~mask; }
