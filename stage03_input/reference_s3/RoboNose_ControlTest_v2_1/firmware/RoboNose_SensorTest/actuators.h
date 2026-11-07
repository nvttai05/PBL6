#pragma once
#include <stdint.h>

struct ActuatorState {
    uint8_t pumpPct = 0;
    uint16_t pumpDuty = 0;
    bool valveEnergized = false;
    bool failsafe = false;
    bool ready = false;
    uint32_t revision = 0;
};

struct ActuatorIO {
    bool (*pump)(uint16_t logicalDuty);
    void (*valve)(bool energized);
};

// Logic independent of Arduino, so the watchdog and output transitions are testable.
class ActuatorController {
public:
    ActuatorController(ActuatorIO io, uint64_t timeoutMs) : io_(io), timeout_(timeoutMs) {}
    void begin(bool ready, uint64_t now);
    const char* setPump(int percent, uint64_t now);
    const char* setValve(int energized, uint64_t now);
    bool allOff(uint64_t now, bool failsafe = false);
    void heartbeat(uint64_t now) { lastHeartbeat_ = now; lease_ = true; }
    bool tick(uint64_t now);
    uint64_t leaseRemaining(uint64_t now) const;
    const ActuatorState& state() const { return state_; }
private:
    void hardwareFault(uint64_t now);
    ActuatorIO io_;
    ActuatorState state_{};
    uint64_t timeout_, lastHeartbeat_ = 0;
    bool lease_ = false;
};
