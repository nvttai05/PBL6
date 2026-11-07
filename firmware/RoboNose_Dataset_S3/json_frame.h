#pragma once
#include <Arduino.h>
#include <math.h>
#include <inttypes.h>
#include "config.h"
class JsonFrame {
public:
    JsonFrame() { buffer.reserve(Config::MAX_FRAME); }
    void begin(const char* type) { buffer="{"; first=true; text("type",type); }
    void text(const char* key,const char* value) { prefix(key); quote(value); }
    void boolean(const char* key,bool value) { prefix(key); buffer+=value?"true":"false"; }
    void integer(const char* key,int64_t value) { char b[32]; snprintf(b,sizeof(b),"%" PRId64,value); prefix(key); buffer+=b; }
    void number(const char* key,double value) { prefix(key); if(!isfinite(value)) { buffer+="null"; return; } char b[64]; snprintf(b,sizeof(b),"%.9f",value); buffer+=b; }
    void nullValue(const char* key) { prefix(key); buffer+="null"; }
    const String& finish() { buffer+="}\n"; return buffer; }
private:
    void prefix(const char* key) { if(!first) buffer+=','; first=false; quote(key); buffer+=':'; }
    void quote(const char* text) { buffer+='"'; for(const unsigned char* p=reinterpret_cast<const unsigned char*>(text);*p;++p) {
        if(*p=='"'||*p=='\\') { buffer+='\\'; buffer+=static_cast<char>(*p); }
        else if(*p<32) { char b[7]; snprintf(b,sizeof(b),"\\u%04x",*p); buffer+=b; } else buffer+=static_cast<char>(*p);
    } buffer+='"'; }
    String buffer; bool first=true;
};
