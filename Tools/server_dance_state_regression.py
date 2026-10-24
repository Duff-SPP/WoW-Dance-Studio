import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import argparse
parser = argparse.ArgumentParser(description='Run the dance-state harness against a patched server checkout.')
parser.add_argument('--core', type=Path, required=True, help='Server source checkout; requires git and a C++20 compiler')
ROOT = parser.parse_args().core.resolve()
source_path = 'src/server/game/Handlers/ChatHandler.cpp'
source = (ROOT / source_path).read_text(encoding='utf-8')
helpers = source[source.index('namespace\n{\n    bool IsAdditionalDanceState'):source.index('void WorldSession::HandleEmoteOpcode')]
opcode = source[source.index('void WorldSession::HandleEmoteOpcode'):source.index('namespace Acore\n{\n    class EmoteChatBuilder')]

def dispatch(text):
    start = text.index('    switch (emote_anim)', text.index('void WorldSession::HandleTextEmoteOpcode'))
    end = text.index('    Unit* unit =', start)
    return 'void WorldSession::Text(uint32 emote_anim)\n{\n' + text[start:end] + '}\n'

fixture = r'''
#include <cassert>
#include <map>
using uint32 = unsigned;
constexpr uint32 EMOTE_ONESHOT_NONE=0, EMOTE_ONESHOT_WAVE=3, EMOTE_STATE_DANCE=10;
constexpr uint32 EMOTE_STATE_SLEEP=12, EMOTE_STATE_SIT=13, EMOTE_STATE_KNEEL=68;
constexpr uint32 UNIT_NPC_EMOTESTATE=83, UNIT_STATE_DIED=1;
struct EmotesEntry { uint32 Flags, EmoteType, UnitStandState; };
struct Store {
    std::map<uint32, EmotesEntry> rows;
    EmotesEntry const* LookupEntry(uint32 id) const {
        auto itr = rows.find(id);
        return itr == rows.end() ? nullptr : &itr->second;
    }
} sEmotesStore;
struct Player {
    uint32 state=0, sent=9999; bool alive=true, died=false, spectator=false;
    bool IsSpectator() const {return spectator;}
    bool IsAlive() const {return alive;}
    bool HasUnitState(uint32) const {return died;}
    uint32 GetUInt32Value(uint32) const {return state;}
    void SetUInt32Value(uint32, uint32 id) {state=id;}
    void HandleEmoteCommand(uint32 id) {sent=id;}
};
namespace WorldPackets::Chat {struct EmoteClient {uint32 EmoteID;};}
struct Scripts {void OnPlayerEmote(Player*, uint32) {}} scripts;
auto sScriptMgr = &scripts;
struct WorldSession {
    Player* _player;
    Player* GetPlayer() {return _player;}
    void HandleEmoteOpcode(WorldPackets::Chat::EmoteClient&);
    void Text(uint32);
};
'''
cases = r'''
int main() {
    sEmotesStore.rows = {{10,{28801,2,0}}, {1088,{28801,2,0}}, {1089,{28801,2,0}},
                        {3,{0,0,0}}, {1100,{28801,0,0}}, {1101,{28801,2,1}}, {1102,{1,2,0}}};
    Player player; WorldSession session{&player};
    for (auto id : {1088u,1089u}) {
        player.state=0; player.sent=9999; session.Text(id);
        assert(player.state==id && player.sent==9999);
        session.Text(id); assert(player.state==id);
        WorldPackets::Chat::EmoteClient stop{0}; session.HandleEmoteOpcode(stop);
        assert(player.state==0 && player.sent==0);
        player.state=id; session.Text(3); assert(player.state==0 && player.sent==3);
        for (auto clear : {0u,12u,13u,68u}) {
            player.state=id; session.Text(clear); assert(player.state==0);
        }
        player.state=id; WorldPackets::Chat::EmoteClient wave{3}; session.HandleEmoteOpcode(wave);
        assert(player.state==0 && player.sent==3);
        player.state=id; WorldPackets::Chat::EmoteClient invalid{1089}; session.HandleEmoteOpcode(invalid);
        assert(player.state==id);
    }
    player.state=0; session.Text(10); assert(player.state==10);
    WorldPackets::Chat::EmoteClient stop{0}; session.HandleEmoteOpcode(stop); assert(player.state==10);
    for (auto id : {3u,1100u,1101u,1102u,99999u}) {
        player.state=0; session.Text(id); assert(player.state==0 && player.sent==id);
    }
    player.state=0; player.died=true; session.Text(1088); assert(player.state==0);
    player.state=1088; session.HandleEmoteOpcode(stop); assert(player.state==1088);
    player.died=false; player.alive=false; session.HandleEmoteOpcode(stop); assert(player.state==1088);
    player.alive=true; player.spectator=true; session.HandleEmoteOpcode(stop); assert(player.state==1088);
    player.spectator=false;
    sEmotesStore.rows.erase(10); player.state=0; session.Text(1088);
    assert(player.state==0 && player.sent==1088);
}
'''
compiler = shutil.which(os.environ.get('CXX', 'cl.exe' if os.name == 'nt' else 'c++'))
assert compiler, 'C++20 compiler required'
baseline = subprocess.run(['git', 'show', 'HEAD:' + source_path], cwd=ROOT, text=True,
                          capture_output=True, check=True).stdout
with tempfile.TemporaryDirectory(prefix='dance-state-') as directory:
    out = Path(directory)
    for name, text in [('baseline', baseline), ('candidate', source)]:
        cpp = out / (name + '.cpp')
        exe = out / (name + ('.exe' if os.name == 'nt' else ''))
        cpp.write_text(fixture + helpers + opcode + dispatch(text) + cases, encoding='utf-8')
        flags = (['/nologo', '/std:c++20', '/EHsc', str(cpp), '/Fe' + str(exe)]
                 if Path(compiler).stem.lower() == 'cl' else ['-std=c++20', str(cpp), '-o', str(exe)])
        subprocess.run([compiler, *flags], cwd=out, check=True, timeout=120)
        result = subprocess.run([str(exe)], cwd=out, capture_output=True, timeout=30)
        assert (result.returncode != 0) if name == 'baseline' else (result.returncode == 0), result.stderr
        print(name + ': ' + ('reproduces one-shot failure' if name == 'baseline' else 'persistent states and interruptions passed'))
