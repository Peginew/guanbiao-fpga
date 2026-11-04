#include "mroi_cold_start.h"
#include "meter_mcu_roi_abi.h"
#include "meter_mcu_live_abi.h"
#include "reader_runtime.h"

/* No image reads, repeated ARM, reset, peripheral setup or memory ownership
 * changes. CPU SDK startup/trap/SP/GP/BSS setup must already be complete.
 * Failure returns to the app's existing fatal stop, never to a retry loop.
 */
int mroi_cold_start(const mroi_io *io,volatile uint32_t diag[4]) {
    uint32_t start,id,abi,live,armed,features;
    if(!io||!io->cycles||!io->read32||!io->write32||!io->fence)return MROI_BOOT_IO_ERROR;
    diag[0]=1;diag[1]=0;diag[2]=0;diag[3]=0;
    start=io->cycles(io->context);
    while((uint32_t)(io->cycles(io->context)-start)<MROI_COLD_WARMUP_CYCLES){}
    io->fence(io->context);diag[0]=2;
    if(!io->read32(io->context,MROI_ID,&id)||
       !io->read32(io->context,MROI_ABI,&abi)||
       !io->read32(io->context,MROI_LIVE_MAGIC,&live)||
       !io->read32(io->context,MROI_COLD_ARM_OFFSET,&armed)||
       !io->read32(io->context,MROI_FEATURES,&features))return diag[1]=MROI_BOOT_IO_ERROR;
    if(id!=MROI_ID_VALUE)return diag[1]=MROI_BOOT_BAD_ID;
    if(abi!=MROI_ABI_VALUE)return diag[1]=MROI_BOOT_BAD_ABI;
    if(live!=MROI_LIVE_MAGIC_VALUE)return diag[1]=MROI_BOOT_BAD_LIVE_ID;
    if(!(features&MROI_FEATURE_PSI_Q8_V1))return diag[1]=MROI_BOOT_MISSING_PSI_FEATURE;
    if(armed!=0)return diag[1]=MROI_BOOT_ALREADY_ARMED;
    io->fence(io->context);diag[0]=3;diag[2]=1;
    if(!io->write32(io->context,MROI_COLD_ARM_OFFSET,MROI_COLD_ARM_MAGIC))return diag[1]=MROI_BOOT_IO_ERROR;
    io->fence(io->context);
    if(!io->read32(io->context,MROI_COLD_ARM_OFFSET,&armed))return diag[1]=MROI_BOOT_IO_ERROR;
    diag[3]=armed;
    if(armed!=1)return diag[1]=MROI_BOOT_ARM_VERIFY;
    diag[0]=4;return diag[1]=MROI_BOOT_OK;
}
