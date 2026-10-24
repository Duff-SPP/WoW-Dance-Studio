#if ASCENSION_ANIMATION_SAFETY
// Optional compatibility fix for the stock resolver's fixed stack array and unbounded hash probe.
#include "AscAnimationSafety.hpp"
#include "AscRuntime.hpp"
#include "AscLog.hpp"
#include <windows.h>
#include <cstring>

namespace AscAnimationSafety
{
    namespace
    {
        ModelView View(const uint8_t* header)
        {
            if (!header) return {};
            return {*reinterpret_cast<const uint8_t* const*>(header + 0x20),
                    *reinterpret_cast<const uint32_t*>(header + 0x1C),
                    *reinterpret_cast<const uint16_t* const*>(header + 0x28),
                    *reinterpret_cast<const uint32_t*>(header + 0x24)};
        }
        bool Lookup(uint32_t id, Row& row)
        {
            const int32_t minimum = *reinterpret_cast<const int32_t*>(0xAD30D8);
            const int32_t maximum = *reinterpret_cast<const int32_t*>(0xAD30D4);
            if (minimum < 0 || maximum < minimum || id > 65535 || id < uint32_t(minimum) || id > uint32_t(maximum))
                return false;
            auto records = *reinterpret_cast<const uint32_t* const* const*>(0xAD30E8);
            if (!records || !records[id - minimum]) return false;
            const uint32_t* record = records[id - minimum];
            row = {record[4], record[5]};
            return true;
        }
        int __fastcall Has(void*, void*, const uint8_t* header, uint32_t id)
        {
            return View(header).Has(id) ? 1 : 0;
        }
        Result* __fastcall ResolveNative(const uint8_t* object, void*, Result* out, uint32_t id)
        {
            if (!out) return nullptr;
            const uint8_t* shared = object ? *reinterpret_cast<const uint8_t* const*>(object + 0x2C) : nullptr;
            const uint8_t* header = shared ? *reinterpret_cast<const uint8_t* const*>(shared + 0x150) : nullptr;
            *out = Resolve(View(header), id, Lookup);
            return out;
        }
    }
    bool Install()
    {
        static bool installed = false;
        if (installed) return true;
        const unsigned char has[] = {0x55,0x8B,0xEC,0x83,0xEC,0x08};
        const unsigned char resolver[] = {0x55,0x8B,0xEC,0x81,0xEC,0xF4,0x07,0x00,0x00};
        if (std::memcmp(reinterpret_cast<void*>(0x825E00), has, sizeof(has)) ||
            std::memcmp(reinterpret_cast<void*>(0x826350), resolver, sizeof(resolver)))
        {
            AscLog::Printf("animation-safety: unexpected native prologue; count expansion refused");
            return false;
        }
        AscRuntime::ReplaceFunction(0x825E00, reinterpret_cast<void*>(&Has));
        AscRuntime::ReplaceFunction(0x826350, reinterpret_cast<void*>(&ResolveNative));
        installed = true;
        AscLog::Printf("animation-safety: bounded model lookup and uint16-safe fallback resolver installed (WDS test)");
        return true;
    }
}

#endif
