#include <cassert>
#include <cstdio>
#include <cstring>
#include "trial_engine.h"
uint16_t duty=999; bool valve=true;
bool pump(uint16_t value) { duty=value; return true; }
void route(bool value) { valve=value; }
int main(int argc,char** argv) {
    Dataset::Engine engine({pump,route}); engine.initialize(true,"parity-boot");
    strcpy(engine.beginTicket,"parity-ticket");
    assert(!duty&&!valve);
    assert(argc==2); FILE* fixture=fopen(argv[1],"r"); assert(fixture);
    unsigned long long at; char verb[16],arg[40],expected[24]; unsigned pwm,wantedValve; unsigned id=0;
    while(fscanf(fixture,"%llu %15s %39s %23s %u %u",&at,verb,arg,expected,&pwm,&wantedValve)==6) {
        if(!strcmp(verb,"TICK")) engine.tick(at);
        else {
            char line[192]; snprintf(line,sizeof(line),"@%u parity-boot parity-session %s%s%s",++id,verb,strcmp(arg,"-")?" ":"",strcmp(arg,"-")?arg:"");
            auto request=Dataset::parseRequest(line); auto reply=engine.command(request,at,true); assert(reply.accepted);
            if(!strcmp(verb,"START")) { auto duplicate=engine.command(request,at,true); assert(duplicate.accepted); }
        }
        assert(!strcmp(Dataset::phaseName(engine.state.phase),expected));
        assert(engine.state.pwm==pwm&&engine.state.valve==static_cast<bool>(wantedValve));
    }
    fclose(fixture); assert(engine.pumpStarts==1);
    auto stale=Dataset::parseRequest("@1 old-boot old-session START 00000000-0000-0000-0000-000000000001");
    assert(!engine.command(stale,1000000,true).accepted);
    engine.stop(1000001,true,"fault"); assert(!duty&&!valve&&engine.latched);
    auto ping=Dataset::parseRequest("@9999 parity-boot parity-session PING");
    assert(!engine.command(ping,1000002,true).accepted&&duty==0);
    auto off=Dataset::parseRequest("@1 old-boot old-session OFF");
    assert(engine.command(off,1000003,true).accepted&&duty==0);
    Dataset::Engine lease({pump,route}); lease.initialize(true,"lease-boot");
    strcpy(lease.beginTicket,"lease-ticket");
    auto begin=Dataset::parseRequest("@1 lease-boot lease-session BEGIN lease-ticket");
    assert(lease.command(begin,0,true).accepted&&duty==818);
    auto invalid=Dataset::parseRequest("@2 lease-boot lease-session EXPOSE");
    assert(!lease.command(invalid,14000,true).accepted);
    lease.tick(15000); assert(lease.latched&&duty==0&&!valve);
    assert(!strcmp(lease.state.faultReason,"lease_expired"));
    auto revive=Dataset::parseRequest("@3 lease-boot lease-session PING");
    assert(!lease.command(revive,15001,true).accepted&&duty==0);
    assert(!Dataset::parseRequest("@0 lease-boot sid START x").valid);
    assert(!Dataset::parseRequest("@4294967296 lease-boot sid START x").valid);
    assert(!Dataset::parseRequest("@1 lease-boot sid START arg extra").valid);
    Dataset::Engine observed({pump,route}); observed.initialize(true,"observed-boot");
    strcpy(observed.beginTicket,"observed-ticket");
    assert(observed.command(Dataset::parseRequest("@1 observed-boot observed-session BEGIN observed-ticket"),10000,true).accepted);
    observed.tick(9999); // Cached loop time must not expire a newer heartbeat.
    assert(!observed.latched&&observed.state.pwm==80);
    assert(observed.command(Dataset::parseRequest("@2 observed-boot observed-session PING"),10001,true).accepted);
    observed.tick(10000); assert(!observed.latched&&observed.state.pwm==80);
    assert(observed.command(Dataset::parseRequest("@3 observed-boot observed-session START 00000000-0000-0000-0000-000000000004"),10002,true).accepted);
    observed.tick(10003); assert(observed.state.phase==Dataset::Phase::BASELINE&&duty==818);
    observed.stop(10004,true,"usb_task_stalled_or_queue_full");
    assert(!strcmp(observed.state.faultReason,"usb_task_stalled_or_queue_full"));
    observed.stop(10005,true,"host_off");
    assert(!strcmp(observed.state.faultReason,"usb_task_stalled_or_queue_full"));
    assert(observed.latched&&!duty&&!valve);
    puts("C++ phase parity and OFF/lease bounds passed");
}
