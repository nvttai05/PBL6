#include <cassert>
#include <cstdio>
#include <vector>
#include "framed_tx.h"

uint64_t clockMs=0;
int mode=0,initialStalls=0;
std::vector<uint8_t> sent;
uint64_t now() { return clockMs; }
void pause() { ++clockMs; }
int write(const uint8_t* bytes,size_t length,uint32_t timeout) {
    assert(length<=64&&timeout<=20);
    if(mode==1||initialStalls-->0) { clockMs+=timeout; return 0; }
    if(mode==2) return -1;
    if(mode==3) return length+1;
    ++clockMs;
    size_t count=length>7?7:length;
    sent.insert(sent.end(),bytes,bytes+count);
    return count;
}
bool drain(uint32_t timeout) {
    if(mode==4) { clockMs+=timeout; return false; }
    return true;
}
void reset(int setting) { clockMs=0; mode=setting; initialStalls=0; sent.clear(); }
int main() {
    using namespace Dataset;
    std::vector<uint8_t> frame(3000);
    for(size_t i=0;i<frame.size();++i) frame[i]=i%251;
    StreamIO io{write,drain,now,pause};
    reset(0); initialStalls=3;
    assert(transmitFrame(frame.data(),frame.size(),io)); assert(sent==frame);
    reset(1); assert(!transmitFrame(frame.data(),frame.size(),io)); assert(clockMs<=1000&&sent.empty());
    reset(2); assert(!transmitFrame(frame.data(),frame.size(),io));
    reset(3); assert(!transmitFrame(frame.data(),frame.size(),io));
    reset(4); assert(!transmitFrame(frame.data(),frame.size(),io)); assert(clockMs<=1000);
    puts("Framed TX preserves partial writes and bounds zero-progress/drain waits");
}
