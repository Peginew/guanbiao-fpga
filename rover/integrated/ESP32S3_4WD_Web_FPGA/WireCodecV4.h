#pragma once
#include "GuanbiaoProtocolV4.h"
#include <cstdint>
#include <cstddef>
#include <cstring>
namespace FpgaWire {
constexpr std::size_t SIZE=32;constexpr auto FPGA_BUILD=gb4::cfg::FPGA_BUILD,ESP_BUILD=gb4::cfg::ESP_BUILD;
inline std::uint16_t u16(const std::uint8_t*p){return std::uint16_t(p[0]|std::uint16_t(p[1])<<8);}inline std::int16_t i16(const std::uint8_t*p){return std::int16_t(u16(p));}
inline std::uint32_t u32(const std::uint8_t*p){return std::uint32_t(p[0])|std::uint32_t(p[1])<<8|std::uint32_t(p[2])<<16|std::uint32_t(p[3])<<24;}
inline void put16(std::uint8_t*p,std::uint16_t n){p[0]=std::uint8_t(n);p[1]=std::uint8_t(n>>8);}inline void put32(std::uint8_t*p,std::uint32_t n){for(unsigned i=0;i<4;i++)p[i]=std::uint8_t(n>>(i*8));}
inline bool ahead16(std::uint16_t a,std::uint16_t b){const auto d=std::uint16_t(a-b);return d&&d<0x8000;}inline bool ahead32(std::uint32_t a,std::uint32_t b){const auto d=std::uint32_t(a-b);return d&&d<0x80000000u;}
inline std::uint16_t crc(const std::uint8_t*p,std::size_t n){std::uint16_t c=0xffff;for(std::size_t i=0;i<n;i++){c^=std::uint16_t(p[i])<<8;for(unsigned j=0;j<8;j++)c=std::uint16_t((c<<1)^((c&0x8000)?0x1021:0));}return c;}
inline void seal(std::uint8_t*b){b[0]=0xa5;b[1]=0x5a;b[2]=4;put16(b+30,crc(b+2,28));}
inline bool valid(const std::uint8_t*b){return b[0]==0xa5&&b[1]==0x5a&&b[2]==4&&b[3]>=1&&b[3]<=10&&u16(b+30)==crc(b+2,28);}
inline bool zeros(const std::uint8_t*p,unsigned n){for(unsigned i=0;i<n;i++)if(p[i])return false;return true;}
inline bool contract(const std::uint8_t*b){if(!valid(b)||b[6]>36||b[7])return false;const auto*p=b+20;
 switch(gb4::Msg(b[3])){
 case gb4::Msg::HELLO:return b[6]==0&&(u32(p)==FPGA_BUILD||u32(p)==ESP_BUILD)&&u32(b+16)==gb4::kConfigSignature&&u16(p+4)==127&&p[6]==32&&p[7]==4&&zeros(p+8,2);
 case gb4::Msg::STATE:return zeros(p+6,4);
 case gb4::Msg::START:return (i16(p)==10000||i16(p)==-10000)&&p[2]<=1&&zeros(p+3,7)&&b[6]==0&&u32(b+12)!=0;
 case gb4::Msg::CANCEL:return p[0]<=31&&zeros(p+1,9);
 case gb4::Msg::ACK:return p[2]>=1&&p[2]<=10&&p[3]<=6&&p[4]<=31&&zeros(p+5,5);
 case gb4::Msg::OBSERVATION:return !(u16(p+6)&~2047u)&&p[8]<=10&&p[9]<=31;
 case gb4::Msg::RESULT:return u16(p+6)<=200&&p[8]==3&&p[9]==0;
 case gb4::Msg::FAILURE:return p[4]<=31&&zeros(p+6,4);
 case gb4::Msg::STEP_REQUEST:return b[6]!=0&&u16(p+4)<=1100&&(i16(p+6)==10000||i16(p+6)==-10000)&&(u16(p+8)&35)==35&&!(u16(p+8)&~35u);
 case gb4::Msg::STOP_ACTION:return !(u16(p+6)&~31u)&&p[8]<=31&&!p[9];
 }return false;
}
}
