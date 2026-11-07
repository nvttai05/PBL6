#include "command_parser.h"
#include <string.h>
#include <stdlib.h>
#include <errno.h>
#include <limits.h>

namespace {
bool unsignedNumber(const char* text, uint32_t& result) {
    if (!text || !*text) return false;
    for (const char* p = text; *p; ++p) if (*p < '0' || *p > '9') return false;
    errno = 0;
    char* end = nullptr;
    const unsigned long value = strtoul(text, &end, 10);
    if (errno || *end || value > UINT32_MAX) return false;
    result = static_cast<uint32_t>(value);
    return true;
}
}

const char* commandName(CommandKind kind) {
    switch (kind) {
    case CommandKind::Info: return "INFO";
    case CommandKind::Ping: return "PING";
    case CommandKind::Help: return "HELP";
    case CommandKind::Pump: return "PUMP";
    case CommandKind::Valve: return "VALVE";
    case CommandKind::AllOff: return "ALL_OFF";
    default: return "INVALID";
    }
}

Command parseCommand(char* line) {
    Command out;
    char* context = nullptr;
    const char* tokens[5];
    unsigned count = 0;
    for (char* token = strtok_r(line, " \t", &context); token; token = strtok_r(nullptr, " \t", &context)) {
        if (count >= 5) { out.error = "too_many_arguments"; return out; }
        tokens[count++] = token;
    }
    unsigned offset = 0;
    if (count && tokens[0][0] == '@') {
        if (!unsignedNumber(tokens[0] + 1, out.requestId) || !out.requestId) {
            out.error = "invalid_request_id"; return out;
        }
        offset = 1;
    }
    if (offset == count) return out;
    const char* name = tokens[offset];
    const unsigned args = count - offset - 1;
    if (!strcmp(name, "INFO") && args == 0) out.kind = CommandKind::Info;
    else if (!strcmp(name, "PING") && args == 0) out.kind = CommandKind::Ping;
    else if (!strcmp(name, "HELP") && args == 0) out.kind = CommandKind::Help;
    else if ((!strcmp(name, "ALL_OFF") && args == 0) ||
             (!strcmp(name, "ALL") && args == 1 && !strcmp(tokens[offset + 1], "OFF"))) out.kind = CommandKind::AllOff;
    else if ((!strcmp(name, "PUMP") || !strcmp(name, "VALVE")) && args == 1) {
        const bool pump = !strcmp(name, "PUMP");
        const char* arg = tokens[offset + 1];
        uint32_t value;
        if (!strcmp(arg, "OFF")) value = 0;
        else if (!strcmp(arg, "ON")) value = pump ? 100 : 1;
        else if (!unsignedNumber(arg, value)) { out.error = "value_must_be_integer"; return out; }
        if (value > (pump ? 100u : 1u)) { out.error = "value_out_of_range"; return out; }
        out.value = static_cast<int>(value);
        out.kind = pump ? CommandKind::Pump : CommandKind::Valve;
    }
    if (out.kind != CommandKind::Invalid) out.error = "";
    return out;
}
