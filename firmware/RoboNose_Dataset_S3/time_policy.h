#pragma once
#include <stdint.h>

namespace Dataset {
// Boot time is 64 bit and does not wrap during a session. A timestamp sampled
// by another task may be newer than this loop's observation; that is not a
// timeout. Guard the subtraction so it cannot underflow to an enormous age.
constexpr uint64_t elapsedMs(uint64_t now, uint64_t since) {
    return now >= since ? now - since : 0;
}
}
