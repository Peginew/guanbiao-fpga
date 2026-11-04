/* Host-only ABI transport fixture. No learned functions/board actions. */
#include "reader_runtime.h"
#include "mroi_cold_start.h"
#include "meter_mcu_roi_abi.h"
#include "meter_mcu_live_abi.h"
#include <stdio.h>
#include <string.h>
typedef struct {uint32_t registers[0x200/4],write_offset[64],write_value[64],writes,clock,claimed,revoked,crc;} fixture;
static uint32_t psi_word;
uint32_t mroi_reader_psi_word(void){return psi_word;}
static int read32(void*p,uint32_t off,uint32_t*v){fixture*f=p;
    if(off>=MROI_DATA&&off<=MROI_DATA_LAST_WORD){*v=0;return !f->revoked;}
    if(off==MROI_STATUS){*v=MROI_STATUS_VISIBLE|(f->claimed?MROI_STATUS_CLAIMED:0)|(f->revoked?MROI_STATUS_REVOKED:0);return 1;}
    if(off>=0x200)return 0;*v=f->registers[off/4];return 1;
}
static int write32(void*p,uint32_t off,uint32_t v){fixture*f=p;
    if(f->writes>=64)return 0;f->write_offset[f->writes]=off;f->write_value[f->writes++]=v;
    if(off==MROI_CLAIM_COMMIT)f->claimed=1;
    if(off==MROI_RETURN_COMMIT||off==MROI_QUIET_COMMIT)f->claimed=0;
    if(off==MROI_COLD_ARM_OFFSET)f->registers[off/4]=v==MROI_COLD_ARM_MAGIC?1:v;
    return 1;
}
static void fence(void*p){(void)p;}
static uint32_t cycles(void*p){fixture*f=p;f->clock+=5000001;return f->clock;}
static int begin(void*p,const mroi_descriptor*d){(void)p;(void)d;psi_word=0;return 1;}
static int feed(void*p,uint32_t i,uint32_t w){(void)p;(void)i;(void)w;return 1;}
static int finish(void*p,int(*permit)(void*),void*c,uint32_t*code){(void)p;if(!permit(c))return 0;psi_word=0x80000800u;*code=0x80000000u|(220u<<22)|(1024u<<11)|1024u;return 1;}
static void cancel(void*p){(void)p;psi_word=0;}
static void init(fixture*f){unsigned i;memset(f,0,sizeof(*f));f->registers[MROI_ID/4]=MROI_ID_VALUE;f->registers[MROI_ABI/4]=MROI_ABI_VALUE;
    f->registers[MROI_LIVE_MAGIC/4]=MROI_LIVE_MAGIC_VALUE;f->registers[MROI_FEATURES/4]=MROI_FEATURE_PSI_Q8_V1;
    f->registers[MROI_SEQUENCE/4]=7;f->registers[MROI_EPOCH/4]=8;f->registers[MROI_SOURCE/4]=9;f->registers[MROI_JOB/4]=10;
    f->registers[MROI_TARGET/4]=11;f->registers[MROI_CONFIG/4]=12;f->registers[MROI_SHAPE/4]=0x00800080;
    f->registers[MROI_STRIDE/4]=2;f->registers[MROI_RADIUS/4]=48;f->registers[MROI_FORMAT/4]=1;f->registers[MROI_BYTES/4]=16384;
    f->registers[MROI_LIVE_QUALITY/4]=MROI_LIVE_SCAN_COMPLETE;f->crc=0xffffffffu;
    for(i=0;i<4096;i++)f->crc=mroi_crc_word(f->crc,0);f->registers[MROI_LIVE_HWCRC/4]=f->crc^0xffffffffu;
}
#define CHECK(x) do{if(!(x)){printf("FAIL line%u\n",(unsigned)__LINE__);return 1;}checks++;}while(0)
int main(void){fixture f;volatile uint32_t cold[4];volatile mroi_diagnostics diag;unsigned checks=0,i,psi=99,code=99,commit=99;
    mroi_io io={&f,read32,write32,fence,cycles,0};mroi_consumer stage={0,begin,feed,finish,cancel};
    init(&f);CHECK(mroi_cold_start(&io,cold)==MROI_BOOT_OK);CHECK(f.writes==1&&f.write_offset[0]==0x060);
    init(&f);f.registers[MROI_FEATURES/4]=0;CHECK(mroi_cold_start(&io,cold)==MROI_BOOT_MISSING_PSI_FEATURE);CHECK(f.writes==0);
    init(&f);memset((void*)&diag,0,sizeof(diag));CHECK(mroi_process_one_with_consumer(&io,&diag,&stage)==MROI_COMPLETED);
    for(i=0;i<f.writes;i++){if(f.write_offset[i]==MROI_RETURN_PSI_Q8)psi=i;if(f.write_offset[i]==MROI_RETURN_CODE)code=i;if(f.write_offset[i]==MROI_RETURN_COMMIT)commit=i;}
    CHECK(psi<code&&code<commit);CHECK(f.write_value[psi]==0x80000800u);CHECK(diag.completed==1&&diag.bytes==16384);
    init(&f);f.registers[MROI_LIVE_HWCRC/4]^=1;memset((void*)&diag,0,sizeof(diag));CHECK(mroi_process_one_with_consumer(&io,&diag,&stage)==MROI_COMPLETED);
    for(i=0;i<f.writes;i++)if(f.write_offset[i]==MROI_RETURN_PSI_Q8)CHECK(f.write_value[i]==0);
    CHECK(diag.return_code==3);CHECK(mroi_guard_recovery(5,100,0x80000064u,1,0x80000064u,1,0x80000000u,100,200,300,400)==300);
    CHECK(mroi_guard_recovery(7,200,0x80000124u,1,0x80000124u,2,0x80000000u,100,200,300,400)==400);
    printf("PASS %u lifecycle/PSIABI checks; no model or device\n",checks);return 0;
}
