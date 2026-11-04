/* Freestanding byte helpers, no syscalls, allocator, file or UART runtime. */
#include <stddef.h>
void *memcpy(void *restrict dest,const void *restrict source,size_t n) {
    unsigned char *d=dest;const unsigned char *s=source;size_t i;
    for(i=0;i<n;i++)d[i]=s[i];
    return dest;
}
void *memset(void *dest,int value,size_t n) {
    unsigned char *d=dest;size_t i;
    for(i=0;i<n;i++)d[i]=(unsigned char)value;
    return dest;
}
