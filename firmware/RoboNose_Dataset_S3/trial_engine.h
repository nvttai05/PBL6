#pragma once
#include <stdint.h>
#include <stddef.h>

namespace Dataset {
enum class Phase { OFF, MONITOR, BASELINE, WAIT_EXPOSURE, EXPOSURE, WAIT_RECOVERY,
                   RECOVERY, WAIT_FINISH, WAIT_NAME, CLOSED, ERROR };
const char* phaseName(Phase phase);
struct Context {
    Phase phase=Phase::OFF;
    uint64_t started=0, deadline=0;
    uint32_t epoch=0, segment=0, trialIndex=0;
    uint8_t pwm=0;
    bool valve=false;
    char trial[37]{}, status[10]="ACTIVE";
    char faultReason[64]{};
};
struct Transition {
    Context before, after;
    uint64_t effective=0, processed=0, barrier=0;
};
struct Request { uint32_t id=0; char boot[33]{}, session[37]{}, verb[16]{}, arg[40]{}; bool valid=false; };
bool identifier(const char* value, size_t maxLength);
Request parseRequest(const char* line);
struct Reply { uint32_t id=0; bool accepted=false; const char* reason="invalid_command"; Context context; uint64_t applied=0, barrier=0; };
struct IO { bool (*pump)(uint16_t); void (*valve)(bool); };
class Engine {
public:
    Engine(IO io, void (*event)(const Transition&, void*)=nullptr, void* user=nullptr)
      : io_(io), event_(event), user_(user) {}
    void initialize(bool ready, const char* boot);
    void tick(uint64_t now);
    Reply command(const Request& request, uint64_t now, bool sensorsReady);
    void stop(uint64_t now, bool fault, const char* reason);
    Context state;
    char boot[33]{}, session[37]{};
    char beginTicket[33]{};
    bool ready=false, latched=false;
    uint64_t scanBarrier=0;
    uint32_t pumpStarts=0;
private:
    void transition(Phase next, uint64_t effective, uint64_t processed, uint64_t duration=0);
    bool applyOutputs(uint64_t now);
    IO io_;
    void (*event_)(const Transition&, void*);
    void* user_;
    uint64_t heartbeat_=0;
    uint32_t highest_=0;
    char cacheSession_[37]{};
    struct Cached { uint32_t id=0, hash=0; Reply reply; } cache_[16];
    unsigned cacheIndex_=0;
};
}
