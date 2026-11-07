#pragma once
#include <Arduino.h>
#include <math.h>
#include <inttypes.h>

// Small flat JSON writer: no external Arduino libraries needed.
class JsonLine {
public:
    JsonLine() { buffer_.reserve(2300); }
    void begin(const char* type) { buffer_ = "{"; first_ = true; text("type", type); }
    void text(const char* key, const char* value) { prefix(key); quote(value); }
    void boolean(const char* key, bool value) { prefix(key); buffer_ += value ? "true" : "false"; }
    void integer(const char* key, int64_t value) {
        char tmp[32]; snprintf(tmp, sizeof(tmp), "%" PRId64, value); prefix(key); buffer_ += tmp;
    }
    void number(const char* key, double value, unsigned decimals = 6) {
        prefix(key);
        if (!isfinite(value)) { buffer_ += "null"; return; }
        char tmp[64]; snprintf(tmp, sizeof(tmp), "%.*f", static_cast<int>(decimals), value);
        buffer_ += tmp;
    }
    void nullValue(const char* key) { prefix(key); buffer_ += "null"; }
    void send() { buffer_ += '}'; Serial.println(buffer_); }
private:
    void prefix(const char* key) { if (!first_) buffer_ += ','; first_ = false; quote(key); buffer_ += ':'; }
    void quote(const char* text) {
        buffer_ += '"';
        for (const unsigned char* p = reinterpret_cast<const unsigned char*>(text); *p; ++p) {
            if (*p == '"' || *p == '\\') { buffer_ += '\\'; buffer_ += static_cast<char>(*p); }
            else if (*p < 32) { char tmp[7]; snprintf(tmp, sizeof(tmp), "\\u%04x", *p); buffer_ += tmp; }
            else buffer_ += static_cast<char>(*p);
        }
        buffer_ += '"';
    }
    String buffer_;
    bool first_ = true;
};
