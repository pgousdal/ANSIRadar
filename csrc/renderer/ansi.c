#include "ansiradar80/ansi.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

static int append_text(char *out, size_t cap, size_t *used, const char *format, ...) {
    int written;
    va_list args;
    if (*used >= cap) {
        return 0;
    }
    va_start(args, format);
    written = vsnprintf(out + *used, cap - *used, format, args);
    va_end(args);
    if (written < 0 || (size_t)written >= cap - *used) {
        return 0;
    }
    *used += (size_t)written;
    return 1;
}

static int append_cell(char *out, size_t cap, size_t *used, int x, int y,
                       ScreenCell cell, int color) {
    if (!append_text(out, cap, used, "\033[%d;%dH", y + 1, x + 1)) {
        return 0;
    }
    if (color && cell.attr != 0 &&
        !append_text(out, cap, used, "\033[0;%dm", 30 + (cell.attr & 7))) {
        return 0;
    }
    if (!append_text(out, cap, used, "%c", cell.ch == 0 ? ' ' : cell.ch)) {
        return 0;
    }
    return color ? append_text(out, cap, used, "\033[0m") : 1;
}

int ansi_full(const Screen *screen, char *output, size_t capacity, int color) {
    size_t used = 0;
    int y;
    int x;
    if (screen == NULL || output == NULL || capacity == 0 ||
        !append_text(output, capacity, &used, "\033[2J\033[H")) {
        return 0;
    }
    for (y = 0; y < screen->height; ++y) {
        for (x = 0; x < screen->width; ++x) {
            if (!append_cell(output, capacity, &used, x, y, screen_get(screen, x, y), color)) {
                return 0;
            }
        }
    }
    return append_text(output, capacity, &used, "\033[0m") ? (int)used : 0;
}

int ansi_diff(const Screen *current, const Screen *previous, char *output,
              size_t capacity, int color) {
    size_t used = 0;
    int y;
    int x;
    if (current == NULL || output == NULL || capacity == 0 || previous == NULL ||
        current->width != previous->width || current->height != previous->height) {
        return ansi_full(current, output, capacity, color);
    }
    for (y = 0; y < current->height; ++y) {
        for (x = 0; x < current->width; ++x) {
            if (memcmp(&current->cells[(size_t)y * current->width + x],
                       &previous->cells[(size_t)y * previous->width + x],
                       sizeof(ScreenCell)) != 0 &&
                !append_cell(output, capacity, &used, x, y, screen_get(current, x, y), color)) {
                return 0;
            }
        }
    }
    return (int)used;
}

void ansi_start(char *output, size_t capacity) {
    if (output != NULL && capacity > 0) {
        snprintf(output, capacity, "\033[?25l");
    }
}

void ansi_stop(char *output, size_t capacity) {
    if (output != NULL && capacity > 0) {
        snprintf(output, capacity, "\033[0m\033[?25h");
    }
}
