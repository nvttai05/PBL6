#pragma once
#include <stdint.h>
#include <stddef.h>
#include "time_policy.h"

namespace Dataset {
struct StreamIO {
    int (*write)(const uint8_t*,size_t,uint32_t);
    bool (*drain)(uint32_t);
    uint64_t (*now)();
    void (*pause)();
};
inline bool transmitFrame(const uint8_t* bytes,size_t length,StreamIO io,uint32_t budgetMs=1000) {
    const uint64_t started=io.now();
    size_t offset=0;
    while(offset<length&&elapsedMs(io.now(),started)<budgetMs) {
        size_t count=length-offset; if(count>64) count=64;
        uint64_t age=elapsedMs(io.now(),started);
        if(age>=budgetMs) break;
        uint32_t timeout=budgetMs-static_cast<uint32_t>(age); if(timeout>20) timeout=20;
        int sent=io.write(bytes+offset,count,timeout);
        if(sent<0||static_cast<size_t>(sent)>count) return false;
        offset+=sent;
        if(!sent) io.pause();
    }
    if(offset!=length) return false;
    while(elapsedMs(io.now(),started)<budgetMs) {
        uint64_t age=elapsedMs(io.now(),started);
        if(age>=budgetMs) break;
        uint32_t timeout=budgetMs-static_cast<uint32_t>(age); if(timeout>20) timeout=20;
        if(io.drain(timeout)) return true;
        io.pause();
    }
    return false;
}
}
