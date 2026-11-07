#pragma once
#include <stdint.h>

namespace Dataset {
constexpr uint32_t USB_STREAM_RX_IRQ=1u<<2, USB_STREAM_TX_IRQ=1u<<3;
constexpr uint32_t USB_STREAM_OWNED_IRQS=USB_STREAM_RX_IRQ|USB_STREAM_TX_IRQ;
struct UsbIrqSnapshot { uint32_t enabled, pending; };

// The stream ISR services RX/TX only. Inherited BUS_RESET/debug interrupts
// must not reach it. RX/TX pending bits must survive driver installation.
template<class Registers>
constexpr UsbIrqSnapshot prepareUsbInterrupts(Registers& registers,uint32_t allMask) {
    UsbIrqSnapshot before{registers.enabled(),registers.pending()};
    registers.disable(allMask);
    registers.clear(allMask & ~USB_STREAM_OWNED_IRQS);
    return before;
}
}
