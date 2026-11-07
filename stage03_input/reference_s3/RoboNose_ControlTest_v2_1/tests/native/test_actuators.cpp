#include <cassert>
#include <cstring>
#include "actuators.h"
#include "command_parser.h"

namespace {
uint16_t pump = 999;
bool valve = true;
bool rejectPwm = false;
bool setPump(uint16_t duty) { pump = duty; return !rejectPwm; }
void setValve(bool energized) { valve = energized; }
Command parse(const char* input) { char copy[128]; std::strcpy(copy, input); return parseCommand(copy); }
}

int main() {
    ActuatorController c({setPump, setValve}, 15000);
    c.begin(true, 0);
    assert(pump == 0 && !valve && c.state().ready);
    assert(!*c.setPump(50, 100) && pump == 512);
    assert(!*c.setValve(1, 200) && valve);
    assert(!c.tick(15199));
    assert(c.tick(15200));
    assert(pump == 0 && !valve && c.state().failsafe);
    c.heartbeat(16000);
    assert(pump == 0 && !valve && c.state().failsafe); // heartbeat cannot restore outputs
    assert(!*c.setPump(100, 17000) && pump == 1023 && !c.state().failsafe);
    assert(*c.setPump(101, 18000) && pump == 1023);
    assert(*c.setValve(2, 19000) && !valve);
    assert(c.tick(32000)); // invalid commands did not renew the lease
    assert(pump == 0);
    c.setValve(1, 33000);
    c.allOff(34000);
    assert(!valve && pump == 0 && !c.state().failsafe);
    c.setPump(80, 35000);
    rejectPwm = true;
    assert(*c.setPump(30, 35001));
    assert(!c.state().ready && c.state().pumpPct == 0 && !valve);
    assert(*c.setValve(1, 35002));
    rejectPwm = false;
    c.allOff(35003);
    assert(!valve && !pump);

    Command p = parse("@12 PUMP 75");
    assert(p.kind == CommandKind::Pump && p.requestId == 12 && p.value == 75);
    assert(parse("PUMP ON").value == 100);
    assert(parse("VALVE OFF").kind == CommandKind::Valve && parse("VALVE OFF").value == 0);
    assert(parse("@31 ALL OFF").kind == CommandKind::AllOff);
    assert(parse("ALL_OFF").kind == CommandKind::AllOff);
    assert(parse("PING").kind == CommandKind::Ping);
    const char* invalid[] = {"PUMP -1", "PUMP 101", "PUMP 0 extra", "PUMP 12.5", "PUMP nan",
                             "VALVE 2", "VALVE -1", "@0 PUMP 20", "@4294967296 PUMP 20", "PUMP", "@1"};
    for (const char* input : invalid) assert(parse(input).kind == CommandKind::Invalid);
}
