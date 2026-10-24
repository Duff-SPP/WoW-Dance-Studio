#define ASCENSION_DANCE_LOOP_REGIONS 1
#include "../src/Ascension/AscDanceLoops.cpp"
#include <cassert>
#include <cstdio>
namespace AscLog { void Printf(const char*, ...) {} }
namespace AscRuntime { void* Detour(uint32_t, uint32_t, void*) { return nullptr; } }
using namespace AscDanceLoops;

// Execute the actual x86 hook bodies against synthetic sampler stack/bone data.
// Only the continuation addresses are replaced; Map and register saves are real.
__declspec(naked) uint32_t PrimaryCall(const uint8_t*, uint8_t*, uint32_t, uint32_t) {
    __asm {
        push ebp
        mov ebp, esp
        sub esp, 70h
        push ebx
        push esi
        push edi
        mov eax, [ebp+8]
        mov [ebp-4], eax
        mov eax, [ebp+10h]
        mov [ebp-64h], eax
        mov edi, [ebp+0Ch]
        mov ecx, [ebp+14h]
        xor edx, edx
        mov primaryReturn, offset done_primary
        jmp Primary
    done_primary:
        div ecx
        mov eax, edx
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret
    }
}
__declspec(naked) uint32_t SecondaryCall(const uint8_t*, uint8_t*, uint32_t, uint32_t) {
    __asm {
        push ebp
        mov ebp, esp
        sub esp, 70h
        push ebx
        push esi
        push edi
        mov eax, [ebp+8]
        mov [ebp-4], eax
        mov eax, [ebp+10h]
        mov [ebp-64h], eax
        mov edi, [ebp+0Ch]
        mov ecx, [ebp+14h]
        xor edx, edx
        mov secondaryReturn, offset done_secondary
        jmp Secondary
    done_secondary:
        div ecx
        mov eax, edx
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret
    }
}
int main() {
    uint8_t data[64]{}, sequence[64]{}, bone[0xAC]{};
    *reinterpret_cast<uint32_t*>(data+0x1C)=1;
    *reinterpret_cast<const uint8_t**>(data+0x20)=sequence;
    *reinterpret_cast<uint16_t*>(sequence)=1798;
    regions[1798]={10367,3400};
    for (uint32_t i=0;i<10000;++i) {
        const auto elapsed=1000+i*6967;
        const auto expected=Phase(elapsed,10367,3400);
        assert(PrimaryCall(data,bone,elapsed,10367)==expected);
        assert(SecondaryCall(data,bone,elapsed,10367)==expected);
    }
    // A stock/nonmatching ID and a differing model duration retain stock modulo.
    *reinterpret_cast<uint16_t*>(sequence)=69;
    assert(PrimaryCall(data,bone,20000,10367)==20000%10367);
    assert(SecondaryCall(data,bone,20000,10367)==20000%10367);
    *reinterpret_cast<uint16_t*>(sequence)=1798;
    assert(PrimaryCall(data,bone,20000,10368)==20000%10368);
    assert(SecondaryCall(data,bone,20000,10368)==20000%10368);
    std::puts("20,000 real x86 sampler hook calls passed; stock/mismatched-duration fallback passed.");
}
