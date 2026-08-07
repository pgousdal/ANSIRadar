#ifndef ANSIRADAR80_SCREEN_H
#define ANSIRADAR80_SCREEN_H

#include <stddef.h>

#define ANSIRADAR80_SCREEN_WIDTH 80
#define ANSIRADAR80_SCREEN_HEIGHT 25

typedef struct {
    unsigned char ch;
    unsigned char attr;
} ScreenCell;

typedef struct {
    int width;
    int height;
    ScreenCell cells[ANSIRADAR80_SCREEN_WIDTH * ANSIRADAR80_SCREEN_HEIGHT];
} Screen;

void screen_clear(Screen *screen, unsigned char ch, unsigned char attr);
void screen_put(Screen *screen, int x, int y, unsigned char ch, unsigned char attr);
void screen_text(Screen *screen, int x, int y, const char *text, unsigned char attr);
ScreenCell screen_get(const Screen *screen, int x, int y);

#endif
