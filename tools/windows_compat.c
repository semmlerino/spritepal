/* Windows compatibility functions */
#include <string.h>
#include <stddef.h>

/* memmem implementation for Windows */
void *memmem(const void *haystack, size_t haystack_len,
             const void *needle, size_t needle_len)
{
    const char *h = haystack;
    const char *n = needle;
    size_t i;

    if (needle_len == 0)
        return (void *)haystack;
    
    if (haystack_len < needle_len)
        return NULL;

    for (i = 0; i <= haystack_len - needle_len; i++) {
        if (memcmp(h + i, n, needle_len) == 0)
            return (void *)(h + i);
    }
    
    return NULL;
}