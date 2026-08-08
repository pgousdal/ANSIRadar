#ifndef ANSIRADAR80_INPUT_H
#define ANSIRADAR80_INPUT_H

#include <stddef.h>

enum InputKey {
    INPUT_NONE = 0,
    INPUT_QUIT,
    INPUT_UP,
    INPUT_DOWN,
    INPUT_LEFT,
    INPUT_RIGHT,
    INPUT_PLUS,
    INPUT_MINUS,
    INPUT_TAB,
    INPUT_SPACE,
    INPUT_ENTER,
    INPUT_ESCAPE,
    INPUT_LIST,
    INPUT_HELP,
};

typedef struct {
    unsigned char bytes[16];
    size_t length;
    unsigned int idle_ticks;
} InputDecoder;

void input_decoder_init(InputDecoder *decoder);
int input_decoder_feed(InputDecoder *decoder, const unsigned char *bytes,
                       size_t length);
int input_decoder_flush(InputDecoder *decoder);
int input_decoder_timeout(InputDecoder *decoder);

#endif
