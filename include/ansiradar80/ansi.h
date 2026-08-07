#ifndef ANSIRADAR80_ANSI_H
#define ANSIRADAR80_ANSI_H

#include <stddef.h>

#include "screen.h"

int ansi_full(const Screen *screen, char *output, size_t capacity, int color);
int ansi_diff(const Screen *current, const Screen *previous, char *output,
              size_t capacity, int color);
void ansi_start(char *output, size_t capacity);
void ansi_stop(char *output, size_t capacity);

#endif
