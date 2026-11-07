#include "actuators.h"

void ActuatorController::begin(bool ready, uint64_t now) {
    state_ = {};
    state_.ready = ready;
    allOff(now);
}

void ActuatorController::hardwareFault(uint64_t now) {
    state_.ready = false;
    allOff(now, true);
}

const char* ActuatorController::setPump(int percent, uint64_t now) {
    if (percent < 0 || percent > 100) return "pump_percent_must_be_0_to_100";
    if (!state_.ready) return "output_hardware_not_ready";
    const uint16_t duty = static_cast<uint16_t>((percent * 1023 + 50) / 100);
    if (!io_.pump(duty)) { hardwareFault(now); return "pwm_write_failed_outputs_off"; }
    if (state_.pumpPct != percent || state_.failsafe) ++state_.revision;
    state_.pumpPct = static_cast<uint8_t>(percent);
    state_.pumpDuty = duty;
    state_.failsafe = false;
    heartbeat(now);
    return "";
}

const char* ActuatorController::setValve(int energized, uint64_t now) {
    if (energized != 0 && energized != 1) return "valve_must_be_0_or_1";
    if (!state_.ready) return "output_hardware_not_ready";
    io_.valve(energized != 0);
    if (state_.valveEnergized != (energized != 0) || state_.failsafe) ++state_.revision;
    state_.valveEnergized = energized != 0;
    state_.failsafe = false;
    heartbeat(now);
    return "";
}

bool ActuatorController::allOff(uint64_t now, bool failsafe) {
    const bool ok = io_.pump(0);
    io_.valve(false);
    if (state_.pumpPct || state_.valveEnergized || state_.failsafe != failsafe) ++state_.revision;
    state_.pumpPct = 0;
    state_.pumpDuty = 0;
    state_.valveEnergized = false;
    state_.failsafe = failsafe;
    if (!ok) state_.ready = false;
    if (failsafe) lease_ = false;
    else heartbeat(now);
    return ok;
}

bool ActuatorController::tick(uint64_t now) {
    if (lease_ && now - lastHeartbeat_ >= timeout_) {
        lease_ = false;
        if (state_.pumpPct || state_.valveEnergized) {
            allOff(now, true);
            return true;
        }
    }
    return false;
}

uint64_t ActuatorController::leaseRemaining(uint64_t now) const {
    if (!lease_ || now - lastHeartbeat_ >= timeout_) return 0;
    return timeout_ - (now - lastHeartbeat_);
}
