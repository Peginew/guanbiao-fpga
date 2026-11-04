/* Dedicated normal32-bit MMIO operations. These are the ONLY recoverable PCs.
 * Exact labels avoid guessing compressed-instruction lengths. Global IRQs stay
 * disabled; no interrupt callback may enter this non-reentrant single-master API.
 */
.option push
.option norvc
.section .text.mroi_guard,"ax",@progbits
.align 2
.global mroi_guard_load,mroi_guard_store
.global mroi_guard_load_pc,mroi_guard_load_wait_pc
.global mroi_guard_store_pc,mroi_guard_store_wait_pc
.global mroi_guard_load_recover,mroi_guard_store_recover
mroi_guard_load:
    la t0,mroi_guard_state
    sw a0,4(t0)
    li t1,1
    sw t1,8(t0)
    sw t1,0(t0)
    fence iorw,iorw
mroi_guard_load_pc:
    lw t1,0(a0)
mroi_guard_load_wait_pc:
    /* Complete the guarded IO read before publishing its data to the caller.
     * The wait instruction is an explicitly exported recovery site, not an
     * inferred arbitrary PC+4. No output store has occurred at this site. */
    fence iorw,iorw
    sw t1,0(a1)
    fence iorw,iorw
    sw zero,0(t0)
    li a0,1
    ret
mroi_guard_load_recover:
    fence iorw,iorw
    la t0,mroi_guard_state
    sw zero,0(t0)
    li a0,0
    ret
mroi_guard_store:
    la t0,mroi_guard_state
    sw a0,4(t0)
    li t1,2
    sw t1,8(t0)
    li t1,1
    sw t1,0(t0)
    fence iorw,iorw
mroi_guard_store_pc:
    sw a1,0(a0)
mroi_guard_store_wait_pc:
    fence iorw,iorw
    sw zero,0(t0)
    li a0,1
    ret
mroi_guard_store_recover:
    fence iorw,iorw
    la t0,mroi_guard_state
    sw zero,0(t0)
    li a0,0
    ret
.option pop
