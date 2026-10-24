#pragma once
#include <cstdint>

namespace AscDanceLoops {
    // Verified sampler replacement: retain the first traversal, then wrap only
    // the cyclic suffix. No timer, emote restart, or per-model mutable clock.
    constexpr uint32_t Phase(uint32_t elapsed, uint32_t duration, uint32_t start) {
        return !duration ? 0 : start >= duration ? elapsed % duration :
            elapsed < duration ? elapsed : start + (elapsed - start) % (duration - start);
    }
    bool Install();
}
