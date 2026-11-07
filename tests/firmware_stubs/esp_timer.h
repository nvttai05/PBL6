#pragma once
#include <stdint.h>
extern uint32_t fake_ms;
inline int64_t esp_timer_get_time() { return static_cast<int64_t>(fake_ms)*1000; }
