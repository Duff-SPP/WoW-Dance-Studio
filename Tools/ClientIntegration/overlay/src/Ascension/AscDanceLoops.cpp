#if ASCENSION_DANCE_LOOP_REGIONS
#include "AscDanceLoopClock.hpp"
#include "AscLog.hpp"
#include "AscRuntime.hpp"
#include <windows.h>
#include <cstring>

namespace AscDanceLoops {
namespace {
    struct Region { uint32_t duration, start; };
    Region regions[65536]{};
    uintptr_t primaryReturn = 0x82F4FF;
    uintptr_t secondaryReturn = 0x82F621;

    bool Load() {
        char path[MAX_PATH]{};
        const DWORD length = GetModuleFileNameA(nullptr, path, MAX_PATH);
        if (!length || length >= MAX_PATH) return false;
        char* slash = std::strrchr(path, '\\');
        if (!slash || size_t(slash - path) + sizeof("\\WoWDanceStudio.loops") > MAX_PATH) return false;
        std::strcpy(slash + 1, "WoWDanceStudio.loops");
        HANDLE file = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (file == INVALID_HANDLE_VALUE) return false;
        struct Header { char magic[8]; uint32_t count; } header{};
        LARGE_INTEGER size{}; DWORD read{};
        bool valid = GetFileSizeEx(file, &size) && ReadFile(file, &header, sizeof(header), &read, nullptr)
            && read == sizeof(header) && !std::memcmp(header.magic, "WDSLOOP1", 8)
            && header.count && header.count <= 65536
            && size.QuadPart == sizeof(header) + uint64_t(header.count) * 12;
        for (uint32_t i = 0; valid && i < header.count; ++i) {
            struct Row { uint32_t id, duration, start; } row{};
            valid = ReadFile(file, &row, sizeof(row), &read, nullptr) && read == sizeof(row)
                && row.id >= 506 && row.id < 65536 && row.duration && row.duration <= 600000
                && row.start < row.duration && !regions[row.id].duration;
            if (valid) regions[row.id] = {row.duration, row.start};
        }
        CloseHandle(file);
        if (!valid) std::memset(regions, 0, sizeof(regions));
        return valid;
    }

    uint32_t __cdecl Map(const uint8_t* data, uint32_t index, uint32_t duration, uint32_t elapsed) {
        // M2Data sequence count/pointer offsets verified in the actual sampler.
        const uint32_t count = *reinterpret_cast<const uint32_t*>(data + 0x1C);
        const auto sequences = *reinterpret_cast<const uint8_t* const*>(data + 0x20);
        if (!sequences || index >= count) return elapsed;
        const auto sequence = sequences + index * 64;
        const auto id = *reinterpret_cast<const uint16_t*>(sequence);
        const auto region = regions[id];
        if (!region.duration || region.duration != duration) return elapsed;
        return Phase(elapsed, duration, region.start);
    }

    // Original instructions and continuations are recorded in
    // Reports/native_montage_sampler.asm (Ascension.exe, Wrath 12340).
    // Patch before DIV, not across its zero-duration branch target.
    __declspec(naked) void Primary() {
        __asm {
            mov eax, [ebp-64h]
            add eax, [edi+5Ch]
            pushfd
            push ecx
            push edx
            push eax
            push ecx
            movzx eax, word ptr [edi+48h]
            push eax
            push dword ptr [ebp-4]
            call Map
            add esp, 16
            pop edx
            pop ecx
            popfd
            jmp dword ptr [primaryReturn]
        }
    }
    __declspec(naked) void Secondary() {
        __asm {
            mov eax, [ebp-64h]
            add eax, [edi+80h]
            pushfd
            push ecx
            push edx
            push eax
            push ecx
            movzx eax, word ptr [edi+6Ch]
            push eax
            push dword ptr [ebp-4]
            call Map
            add esp, 16
            pop edx
            pop ecx
            popfd
            jmp dword ptr [secondaryReturn]
        }
    }
}

bool Install() {
    static bool installed = false;
    if (installed) return true;
    const unsigned char a[] = {0x8B,0x45,0x9C,0x03,0x47,0x5C,0xD9,0x6D,0x0E,0xF7,0xF1,0x8B,0xC2};
    const unsigned char b[] = {0x8B,0x45,0x9C,0x03,0x87,0x80,0,0,0,0xD9,0x6D,0x0E,0xF7,0xF1,0x8B,0xC2};
    if (!Load()) { AscLog::Printf("dance-loop-regions: absent/invalid configuration; stock sampler retained"); return false; }
    if (std::memcmp(reinterpret_cast<void*>(0x82F4F9), a, sizeof(a)) ||
        std::memcmp(reinterpret_cast<void*>(0x82F618), b, sizeof(b))) {
        AscLog::Printf("dance-loop-regions: sampler bytes differ; installation refused"); return false;
    }
    AscRuntime::Detour(0x82F4F9, 6, reinterpret_cast<void*>(&Primary));
    AscRuntime::Detour(0x82F618, 9, reinterpret_cast<void*>(&Secondary));
    installed = true;
    AscLog::Printf("dance-loop-regions: first traversal plus native cyclic suffix enabled (experimental)");
    return true;
}
}
#endif
