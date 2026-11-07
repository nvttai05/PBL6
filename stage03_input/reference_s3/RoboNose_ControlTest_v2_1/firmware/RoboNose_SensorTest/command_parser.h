#pragma once
#include <stdint.h>
enum class CommandKind { Info, Ping, Help, Pump, Valve, AllOff, Invalid };
struct Command {
    CommandKind kind = CommandKind::Invalid;
    uint32_t requestId = 0;
    int value = 0;
    const char* error = "invalid_command";
};
Command parseCommand(char* mutableLine);
const char* commandName(CommandKind kind);
