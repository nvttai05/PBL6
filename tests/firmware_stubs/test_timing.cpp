#include <cstdio>
#include "time_policy.h"
#include "usb_irq_policy.h"

using Dataset::elapsedMs;

struct IrqRegisters {
    uint32_t mask,status;
    constexpr uint32_t enabled() const { return mask; }
    constexpr uint32_t pending() const { return status; }
    constexpr void disable(uint32_t value) { mask&=~value; }
    constexpr void clear(uint32_t value) { status&=~value; }
};
constexpr bool verifiesHandoff(uint32_t mask,uint32_t pending) {
    IrqRegisters registers{mask,pending};
    auto before=Dataset::prepareUsbInterrupts(registers,0x7ffff);
    return before.enabled==mask&&before.pending==pending&&registers.mask==0
        &&registers.status==(pending&Dataset::USB_STREAM_OWNED_IRQS);
}
static_assert(((0x200u|4u)&0x200u)!=0,"old OR-only RX enable leaves BUS_RESET armed");
static_assert(verifiesHandoff(0x200,0x200),"inherited BUS_RESET must be disabled and cleared");
static_assert(verifiesHandoff(0x20c,0x20c),"preserve RX/TX pending flags while removing BUS_RESET");
static_assert(verifiesHandoff(0x7ffff,0x7ffff),"remove all non-stream IRQs, including SOF/debug");
static_assert(verifiesHandoff(0,0),"clean boot remains clean");

// Reproduce the old unsigned subtraction: TX completes 1 ms after the loop's
// cached observation. The old expression mistakes that progress for a stall.
static_assert(uint64_t{4527216} - uint64_t{4527217} > 2000,
              "reproducer must exercise uint64 underflow");
static_assert(elapsedMs(4527216, 4527217) == 0,
              "newer TX progress is not a timeout");
static_assert(elapsedMs(4527217, 4527217) == 0, "same timestamp");
static_assert(elapsedMs(4527218, 4527217) == 1, "normal progress");
static_assert(!(elapsedMs(4529217, 4527217) > 2000), "USB boundary is strict");
static_assert(elapsedMs(4529218, 4527217) > 2000, "real USB stall still trips");
static_assert(elapsedMs(14999, 0) < 15000, "lease before deadline");
static_assert(elapsedMs(15000, 0) >= 15000, "lease expires at deadline");
static_assert(elapsedMs(0x100000001ULL, 0x100000002ULL) == 0,
              "timestamps beyond 32-bit millis remain ordered");
static_assert(elapsedMs(0x100000002ULL, 0x100000001ULL) == 1,
              "64-bit timestamps retain precision");

int main() {
    puts("C++ watchdog age and uint64 underflow assertions passed");
}
