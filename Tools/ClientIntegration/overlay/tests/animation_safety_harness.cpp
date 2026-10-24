#include "Ascension/AscAnimationSafety.hpp"
#include <windows.h>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <fstream>
#include <string>
#include <iterator>
namespace AscAnimationSafety { bool Install(); }
namespace AscLog { void Printf(const char*, ...) {} }
namespace AscRuntime { void ReplaceFunction(uint32_t at, void* fn) { auto p=reinterpret_cast<uint8_t*>(at);p[0]=0xE9;*reinterpret_cast<uint32_t*>(p+1)=uint32_t(reinterpret_cast<uintptr_t>(fn))-at-5;FlushInstructionCache(GetCurrentProcess(),p,5); } }
using namespace AscAnimationSafety;
int checks=0;
void Check(bool value,const char*label){++checks;if(!value){std::printf("FAIL: %s\n",label);std::exit(1);}}
int main(int argc,char**argv){
 std::array<uint8_t,128> sequences{};uint16_t dance=69;std::memcpy(sequences.data()+64,&dance,2);
 std::vector<uint16_t> hash(1794,65535);hash[0]=0;hash[69]=1;ModelView model{sequences.data(),2,hash.data(),uint32_t(hash.size())};
 auto lookup=[](uint32_t id,Row&r){if(id==1792){r={0,69};return true;}return false;};
 auto value=Resolve(model,1792,lookup);Check(value.id==69&&value.type==0,"extended ID fallback");
 value=Resolve(model,69,lookup);Check(value.id==69&&value.type==0,"direct ID");
 value=Resolve(model,0xFFFFFFFFu,lookup);Check(value.id==0,"out of uint16 range");
 value=Resolve(model,65535,lookup);Check(value.id==0,"maximum absent ID");
 value=Resolve(model,1792,[](uint32_t id,Row&r){r={0,id==1792?1793u:1792u};return true;});Check(value.id==0,"cycle terminates");
 value=Resolve(model,1792,[](uint32_t id,Row&r){r={0,id};return true;});Check(value.id==0,"self cycle");
 value=Resolve(model,1792,[](uint32_t,Row&r){r={0x10,69};return true;});Check(value.type==1,"reverse flag");
 value=Resolve(model,1792,[](uint32_t,Row&r){r={0x20,69};return true;});Check(value.type==3,"blend positive");
 value=Resolve(model,1792,[](uint32_t id,Row&r){r=id==1792?Row{0x10,1793}:Row{0x20,69};return true;});Check(value.type==2,"blend zero");
 std::array<uint16_t,1> full{0};ModelView malformed{sequences.data(),2,full.data(),1};Check(!malformed.Has(1792),"collision terminates");
 full[0]=2;Check(!malformed.Has(0),"invalid index");ModelView linear{sequences.data(),2,nullptr,0};Check(linear.Has(69)&&!linear.Has(1792),"linear mode");
 std::array<uint16_t,7> collision;collision.fill(65535);collision[6]=0;collision[0]=1;ModelView quadratic{sequences.data(),2,collision.data(),7};Check(quadratic.Has(69),"squared native probing");
 auto code=VirtualAlloc(reinterpret_cast<void*>(0x820000),0x10000,MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE);
 auto dbc=VirtualAlloc(reinterpret_cast<void*>(0xAD0000),0x10000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);Check(code==reinterpret_cast<void*>(0x820000)&&dbc==reinterpret_cast<void*>(0xAD0000),"fixture memory");
 const uint8_t has[]={0x55,0x8B,0xEC,0x83,0xEC,0x08};const uint8_t resolve[]={0x55,0x8B,0xEC,0x81,0xEC,0xF4,0x07,0,0};
 std::memcpy(reinterpret_cast<void*>(0x825E00),has,sizeof(has));std::memcpy(reinterpret_cast<void*>(0x826350),resolve,sizeof(resolve));
 std::array<uint8_t,0x2C> header{};*reinterpret_cast<uint32_t*>(header.data()+0x1C)=2;*reinterpret_cast<const uint8_t**>(header.data()+0x20)=sequences.data();
 *reinterpret_cast<uint32_t*>(header.data()+0x24)=uint32_t(hash.size());*reinterpret_cast<const uint16_t**>(header.data()+0x28)=hash.data();
 std::array<uint8_t,0x154> shared{};*reinterpret_cast<uint8_t**>(shared.data()+0x150)=header.data();std::array<uint8_t,0x30> object{};*reinterpret_cast<uint8_t**>(object.data()+0x2C)=shared.data();
 std::array<uint32_t,8> row{};row[0]=1792;row[5]=69;std::vector<const uint32_t*> records(1793,nullptr);records[1792]=row.data();
 *reinterpret_cast<int32_t*>(0xAD30D8)=0;*reinterpret_cast<int32_t*>(0xAD30D4)=1792;*reinterpret_cast<const uint32_t***>(0xAD30E8)=records.data();
 *reinterpret_cast<uint8_t*>(0x826350)=0xCC;
 Check(!Install(),"unexpected prologue refused");Check(*reinterpret_cast<uint8_t*>(0x825E00)==0x55,"failed preflight leaves both functions intact");
 *reinterpret_cast<uint8_t*>(0x826350)=0x55;
 Check(Install(),"install production hooks");Check(Install(),"idempotent install");
 using NativeHas=int(__thiscall*)(void*,const uint8_t*,uint32_t);using NativeResolve=Result*(__thiscall*)(void*,Result*,uint32_t);
 auto nativeHas=reinterpret_cast<NativeHas>(0x825E00);auto nativeResolve=reinterpret_cast<NativeResolve>(0x826350);
 Check(nativeHas(object.data(),header.data(),69)==1,"production x86 lookup ABI");Result result{};
 Check(nativeResolve(object.data(),&result,1792)==&result&&result.id==69&&result.type==0,"production x86 fallback ABI");
 for(int i=0;i<10000;++i)nativeResolve(object.data(),&result,1792);Check(result.id==69,"repeated stack correctness");
 if(argc>1){std::ifstream paths(argv[1]);std::string path;int files=0;
 while(std::getline(paths,path)){if(path.empty())continue;std::ifstream input(path,std::ios::binary);std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(input)),std::istreambuf_iterator<char>());
 Check(bytes.size()>=304,"real model readable");uint32_t count,offset,lookupCount,lookupOffset;std::memcpy(&count,bytes.data()+28,4);std::memcpy(&offset,bytes.data()+32,4);std::memcpy(&lookupCount,bytes.data()+36,4);std::memcpy(&lookupOffset,bytes.data()+40,4);
 Check(uint64_t(offset)+uint64_t(count)*64<=bytes.size()&&uint64_t(lookupOffset)+uint64_t(lookupCount)*2<=bytes.size(),"real table bounds");
 ModelView actual{bytes.data()+offset,count,reinterpret_cast<const uint16_t*>(bytes.data()+lookupOffset),lookupCount};
 for(uint32_t slot=0;slot<lookupCount;++slot){auto index=actual.lookup[slot];if(index!=65535){Check(index<count,"real lookup index valid");Check(actual.Has(actual.Id(index)),"real occupied animation resolves");}}
 ++files;}Check(files>0,"real models exercised");std::printf("Real model lookup validation: %d files\n",files);}
 std::printf("PASS: %d safety checks; production x86 hooks; 10000 repeated calls\n",checks);
}
