#include "../src/Ascension/AscDanceLoopClock.hpp"
#include <cassert>
#include <cstdint>
int main() {
    using AscDanceLoops::Phase;
    assert(Phase(0,10367,3400)==0);
    assert(Phase(3399,10367,3400)==3399);
    assert(Phase(3400,10367,3400)==3400);
    assert(Phase(10366,10367,3400)==10366);
    assert(Phase(10367,10367,3400)==3400);
    for (uint32_t i=0;i<10000;++i) {
        assert(Phase(10367+i*6967,10367,3400)==3400);
        assert(Phase(10367+i*6967+123,10367,3400)==3523);
    }
    assert(Phase(10,0,0)==0);
    assert(Phase(25,10,0)==5);
    assert(Phase(25,10,10)==5);
}
