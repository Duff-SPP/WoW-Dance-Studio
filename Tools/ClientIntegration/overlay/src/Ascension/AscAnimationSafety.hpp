#pragma once
#include <bitset>
#include <cstdint>
#include <cstring>

namespace AscAnimationSafety
{
    struct ModelView
    {
        const uint8_t* sequences;
        uint32_t count;
        const uint16_t* lookup;
        uint32_t lookupCount;
        uint16_t Id(uint32_t index) const noexcept
        {
            uint16_t id;
            std::memcpy(&id, sequences + index * 64u, sizeof(id));
            return id;
        }
        bool Has(uint32_t id) const noexcept
        {
            if (!sequences || !count || count > 65535 || id > 65535)
                return false;
            if (!lookupCount)
            {
                for (uint32_t i = 0; i < count; ++i)
                    if (Id(i) == id) return true;
                return false;
            }
            if (!lookup || lookupCount > 65536) return false;
            uint32_t slot = id % lookupCount;
            for (uint32_t probe = 0; probe < lookupCount; ++probe)
            {
                uint16_t index = lookup[slot];
                if (index == 65535 || index >= count) return false;
                if (Id(index) == id) return true;
                // Native 0x825E80 adds successive squared probe numbers to the previous bucket.
                uint32_t step = probe + 1;
                slot = static_cast<uint32_t>((slot + uint64_t(step) * step) % lookupCount);
            }
            return false;
        }
    };
    struct Row { uint32_t flags; uint32_t fallback; };
    struct Result { uint16_t id; uint16_t type; };
    static_assert(sizeof(Result) == 4, "Native resolver result ABI");

    template<class Lookup>
    Result Resolve(const ModelView& model, uint32_t requested, Lookup lookup) noexcept
    {
        const uint16_t base = model.Has(0) ? 0 : model.Has(147) ? 147 :
            model.sequences && model.count ? model.Id(0) : 0;
        if (model.Has(requested)) return {static_cast<uint16_t>(requested), 0};
        std::bitset<65536> visited;
        int direction = 1;
        int balance = 0;
        uint32_t id = requested;
        while (id < visited.size() && !visited[id])
        {
            Row row;
            if (!lookup(id, row) || row.fallback == id) break;
            visited[id] = true;
            if (row.flags & 0x10) { balance += direction; direction = -direction; }
            if (row.flags & 0x20) { balance += direction; direction = 0; }
            id = row.fallback;
            if (model.Has(id))
                return {static_cast<uint16_t>(id), static_cast<uint16_t>(direction > 0 ? 0 : direction < 0 ? 1 : 2 + (balance > 0))};
        }
        return {base, 0};
    }
}
