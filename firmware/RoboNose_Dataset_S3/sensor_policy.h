#pragma once
#include <stdint.h>
namespace SensorPolicy {
inline bool fresh(uint8_t fields,uint8_t status) { return fields>0&&(status&0x80)!=0; }
}
