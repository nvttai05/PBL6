#include "trial_engine.h"
#include "time_policy.h"
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <errno.h>
#include <math.h>
#include <initializer_list>

namespace Dataset {
const char* phaseName(Phase p) {
    static const char* names[]={"OFF","MONITOR","BASELINE","WAIT_EXPOSURE","EXPOSURE",
        "WAIT_RECOVERY","RECOVERY","WAIT_FINISH","WAIT_NAME","CLOSED","ERROR"};
    return names[static_cast<unsigned>(p)];
}
bool identifier(const char* s, size_t limit) {
    if (!s || !*s || strlen(s)>limit) return false;
    for (;*s;++s) if (!((*s>='0'&&*s<='9')||(*s>='a'&&*s<='z')||(*s>='A'&&*s<='Z')||*s=='-'||*s=='_')) return false;
    return true;
}
Request parseRequest(const char* line) {
    Request out;
    if (!line || strlen(line)>=192) return out;
    if (!strcmp(line,"ALL_OFF")) { strcpy(out.verb,"FAULT"); out.valid=true; return out; }
    char buffer[192]; strcpy(buffer,line);
    char* tokens[6]; unsigned n=0; char* cursor=buffer;
    while(*cursor) {
        while(*cursor==' '||*cursor=='\t'||*cursor=='\r') ++cursor;
        if(!*cursor) break;
        if(n==6) return out;
        tokens[n++]=cursor;
        while(*cursor&&*cursor!=' '&&*cursor!='\t'&&*cursor!='\r') ++cursor;
        if(*cursor) *cursor++=0;
    }
    if(n<4||n>5||tokens[0][0]!='@'||!identifier(tokens[1],32)||!identifier(tokens[2],36)) return out;
    if (!tokens[0][1]) return out;
    for(const char* p=tokens[0]+1;*p;++p) if(*p<'0'||*p>'9') return out;
    errno=0; char* end=nullptr; unsigned long long id=strtoull(tokens[0]+1,&end,10);
    if(errno||*end||!id||id>UINT32_MAX||strlen(tokens[3])>=sizeof(out.verb)) return out;
    if(n==5&&strlen(tokens[4])>=sizeof(out.arg)) return out;
    out.id=static_cast<uint32_t>(id); strcpy(out.boot,tokens[1]); strcpy(out.session,tokens[2]); strcpy(out.verb,tokens[3]);
    if(n==5) strcpy(out.arg,tokens[4]);
    out.valid=true; return out;
}
void Engine::initialize(bool initialized, const char* id) {
    state=Context{}; ready=initialized; strncpy(boot,id,sizeof(boot)-1);
    io_.valve(false); if(!io_.pump(0)) ready=false;
}
bool Engine::applyOutputs(uint64_t now) {
    io_.valve(state.valve);
    if(!io_.pump((state.pwm*1023+50)/100)) { ready=false; stop(now,true,"pwm_write_failed"); return false; }
    return true;
}
void Engine::transition(Phase next,uint64_t effective,uint64_t processed,uint64_t duration) {
    Transition change; change.before=state;
    state.phase=next; state.started=effective; state.deadline=duration?effective+duration:0;
    if(next==Phase::MONITOR||next==Phase::CLOSED||next==Phase::ERROR) state.trial[0]=0;
    ++state.epoch; ++state.segment;
    state.valve=next==Phase::MONITOR||next==Phase::BASELINE||next==Phase::WAIT_EXPOSURE||next==Phase::EXPOSURE||next==Phase::WAIT_RECOVERY;
    // Pump duty is changed only by BEGIN/OFF. Transitions merely change route.
    io_.valve(state.valve);
    change.after=state; change.effective=effective; change.processed=processed; change.barrier=scanBarrier;
    if(event_) event_(change,user_);
}
void Engine::stop(uint64_t now,bool fault,const char* reason) {
    state.pwm=0; state.valve=false; state.deadline=0;
    io_.valve(false); if(!io_.pump(0)) { ready=false; fault=true; reason="pwm_write_failed"; }
    if(fault&&!state.faultReason[0]) {
        strncpy(state.faultReason,reason?reason:"unspecified_fault",sizeof(state.faultReason)-1);
        state.faultReason[sizeof(state.faultReason)-1]=0;
    }
    latched=latched||fault;
    if(!strcmp(state.status,"ACTIVE")) strcpy(state.status,fault?"ERROR":"ABORTED");
    if(state.phase!=Phase::ERROR&&state.phase!=Phase::CLOSED) transition(fault?Phase::ERROR:Phase::CLOSED,now,now);
    else if(fault) state.phase=Phase::ERROR;
}
void Engine::tick(uint64_t now) {
    if(state.pwm&&elapsedMs(now,heartbeat_)>=15000) { stop(now,true,"lease_expired"); return; }
    if(state.deadline&&now>=state.deadline) {
        Phase next=state.phase==Phase::BASELINE?Phase::WAIT_EXPOSURE:state.phase==Phase::EXPOSURE?Phase::WAIT_RECOVERY:Phase::WAIT_FINISH;
        transition(next,state.deadline,now);
    }
}
Reply Engine::command(const Request& r,uint64_t now,bool sensorsReady) {
    tick(now); Reply reply; reply.id=r.id; reply.applied=now; reply.context=state; reply.barrier=scanBarrier;
    if(!r.valid) return reply;
    // Emergency OFF bypasses boot/session/ID checks and never waits for TX.
    if(!strcmp(r.verb,"OFF")||!strcmp(r.verb,"FAULT")) {
        stop(now,!strcmp(r.verb,"FAULT"),"host_off"); reply.accepted=true; reply.reason="commanded_off";
        reply.context=state; return reply;
    }
    if(strcmp(r.boot,boot)) { reply.reason="boot_mismatch"; return reply; }
    bool freshBegin=!strcmp(r.verb,"BEGIN")&&(state.phase==Phase::OFF||state.phase==Phase::CLOSED)
        &&beginTicket[0]&&!strcmp(r.arg,beginTicket)&&strcmp(r.session,session)&&!latched;
    if(freshBegin&&strcmp(cacheSession_,r.session)) {
        highest_=0; for(auto& cached:cache_) cached=Cached{};
        strcpy(cacheSession_,r.session);
    } else if(strcmp(r.verb,"BEGIN")&&strcmp(r.session,session)) {
        reply.reason="session_mismatch"; return reply;
    }
    uint32_t hash=2166136261u;
    for(const char* s: {r.session,r.verb,r.arg}) for(;*s;++s) hash=(hash^static_cast<uint8_t>(*s))*16777619u;
    for(const auto& cached:cache_) if(cached.id==r.id) {
        if(cached.hash==hash) return cached.reply;
        reply.reason="request_id_reuse"; return reply;
    }
    if(r.id<=highest_) { reply.reason="request_id_expired"; return reply; }
    highest_=r.id;
    const char* reason="wrong_state_or_arguments";
    if(latched) reason="fault_latched_reset_required";
    else if(!strcmp(r.verb,"BEGIN")&&(state.phase==Phase::OFF||state.phase==Phase::CLOSED)) {
        if(!ready||!sensorsReady) reason="preflight_not_ready";
        else if(!beginTicket[0]||strcmp(r.arg,beginTicket)) reason="begin_ticket_invalid_or_consumed";
        else if(!strcmp(session,r.session)) reason="session_id_reused";
        else { strcpy(session,r.session); beginTicket[0]=0; state.trial[0]=0; state.pwm=80; state.valve=true; heartbeat_=now;
            if(applyOutputs(now)) { ++pumpStarts; transition(Phase::MONITOR,now,now); reason="accepted"; }
            else reason="output_fault"; }
    } else if(strcmp(session,r.session)) reason="session_mismatch";
    else if(!strcmp(r.verb,"PING")&&!r.arg[0]&&state.pwm==80) { heartbeat_=now; reason="accepted"; }
    else if(!strcmp(r.verb,"STATUS")&&!r.arg[0]) reason="accepted";
    else if(!strcmp(r.verb,"MARK")&&!r.arg[0]&&state.pwm) reason="accepted";
    else if(!strcmp(r.verb,"START")&&identifier(r.arg,36)&&state.phase==Phase::MONITOR) {
        strcpy(state.trial,r.arg); strcpy(state.status,"ACTIVE"); ++state.trialIndex;
        transition(Phase::BASELINE,now,now,60000); reason="accepted";
    } else if(!r.arg[0]&&!strcmp(r.verb,"EXPOSE")&&state.phase==Phase::WAIT_EXPOSURE) {
        transition(Phase::EXPOSURE,now,now,120000); reason="accepted";
    } else if(!r.arg[0]&&!strcmp(r.verb,"RECOVER")&&state.phase==Phase::WAIT_RECOVERY) {
        transition(Phase::RECOVERY,now,now,60000); reason="accepted";
    } else if(!strcmp(r.verb,"EXTEND")&&state.phase==Phase::WAIT_FINISH&&r.arg[0]) {
        bool digits=true; for(const char* p=r.arg;*p;++p) if(*p<'0'||*p>'9') digits=false;
        errno=0; char* end=nullptr; unsigned long long duration=strtoull(r.arg,&end,10);
        if(digits&&!errno&&!*end&&duration>0&&duration<=3600000) {
            transition(Phase::RECOVERY,now,now,duration); reason="accepted";
        } else reason="extend_out_of_bounds";
    } else if(!r.arg[0]&&(!strcmp(r.verb,"FINISH")||!strcmp(r.verb,"ABORT"))&&state.phase>=Phase::BASELINE&&state.phase<=Phase::WAIT_FINISH) {
        strcpy(state.status,!strcmp(r.verb,"FINISH")&&state.phase==Phase::WAIT_FINISH?"COMPLETE":"ABORTED");
        transition(Phase::WAIT_NAME,now,now); reason="accepted";
    } else if(!r.arg[0]&&!strcmp(r.verb,"NEXT")&&state.phase==Phase::WAIT_NAME) {
        transition(Phase::MONITOR,now,now); state.trial[0]=0; reason="accepted";
    }
    reply.accepted=!strcmp(reason,"accepted"); reply.reason=reason; reply.context=state;
    cache_[cacheIndex_++%16]={r.id,hash,reply}; return reply;
}
}
