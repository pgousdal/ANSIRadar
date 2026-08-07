#include "ansiradar80/screen.h"

#include <string.h>

void screen_clear(Screen *screen, unsigned char ch, unsigned char attr) {
    size_t i;
    if (screen == NULL) {
        return;
    }
    screen->width = ANSIRADAR80_SCREEN_WIDTH;
    screen->height = ANSIRADAR80_SCREEN_HEIGHT;
    for (i = 0; i < ANSIRADAR80_SCREEN_WIDTH * ANSIRADAR80_SCREEN_HEIGHT; ++i) {
        screen->cells[i].ch = ch;
        screen->cells[i].attr = attr;
    }
}

void screen_put(Screen *screen, int x, int y, unsigned char ch, unsigned char attr) {
    if (screen == NULL || x < 0 || y < 0 || x >= screen->width || y >= screen->height) {
        return;
    }
    screen->cells[(size_t)y * (size_t)screen->width + (size_t)x].ch = ch;
    screen->cells[(size_t)y * (size_t)screen->width + (size_t)x].attr = attr;
}

void screen_text(Screen *screen, int x, int y, const char *text, unsigned char attr) {
    int offset = 0;
    if (text == NULL) {
        return;
    }
    while (text[offset] != '\0') {
        screen_put(screen, x + offset, y, (unsigned char)text[offset], attr);
        ++offset;
    }
}

ScreenCell screen_get(const Screen *screen, int x, int y) {
    ScreenCell blank = {' ', 0};
    if (screen == NULL || x < 0 || y < 0 || x >= screen->width || y >= screen->height) {
        return blank;
    }
    return screen->cells[(size_t)y * (size_t)screen->width + (size_t)x];
}
