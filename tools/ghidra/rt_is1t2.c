/* Round-trip test: Ghidra-decompiled logic re-implemented for pi32v2.
 * Addresses are RAM mirrors (same 32-bit space as flash VA 0x01E00000).
 * SPDX-License-Identifier: MIT */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;

#define STACK_FLAGS (*(volatile u8 *)0x0000BF39)
#define CONN_COUNT  (*(volatile u16 *)0x0001A662)

/* FUN_01e1787c == is_1t2_connection() */
int is_1t2_connection(void)
{
    return (CONN_COUNT & 7) == ((STACK_FLAGS & 0x30) >> 4);
}

/* FUN_01e182b0 == __set_user_ctrl_conn_num(1) -- stock semantics */
void set_conn_num_2(void)
{
    STACK_FLAGS = (STACK_FLAGS & 0xCF) | 0x10;
}
