#include "ansiradar80/input.h"

#include <string.h>

static void drop_bytes(InputDecoder *decoder, size_t count) {
    if (count >= decoder->length) {
        decoder->length = 0;
        return;
    }
    memmove(decoder->bytes, decoder->bytes + count, decoder->length - count);
    decoder->length -= count;
}

void input_decoder_init(InputDecoder *decoder) {
    if (decoder != NULL) {
        memset(decoder, 0, sizeof(*decoder));
    }
}

static int parse_key(InputDecoder *decoder) {
    unsigned char value;
    if (decoder->length == 0) return INPUT_NONE;
    value = decoder->bytes[0];
    if (value == 0xff) {
        if (decoder->length < 2) return INPUT_NONE;
        if (decoder->bytes[1] == 0xfa) {
            size_t i;
            for (i = 2; i + 1 < decoder->length; ++i) {
                if (decoder->bytes[i] == 0xff && decoder->bytes[i + 1] == 0xf0) {
                    drop_bytes(decoder, i + 2);
                    return INPUT_NONE;
                }
            }
            if (decoder->length > 256) decoder->length = 0;
            return INPUT_NONE;
        }
        if (decoder->bytes[1] >= 251 && decoder->bytes[1] <= 254 && decoder->length < 3) {
            return INPUT_NONE;
        }
        drop_bytes(decoder, decoder->bytes[1] >= 251 && decoder->bytes[1] <= 254 ? 3 : 2);
        return INPUT_NONE;
    }
    if (value == 27) {
        if (decoder->length == 1) return INPUT_NONE;
        if (decoder->bytes[1] != '[' && decoder->bytes[1] != 'O') {
            drop_bytes(decoder, 1);
            return INPUT_ESCAPE;
        }
        if (decoder->length < 3) return INPUT_NONE;
        if (decoder->bytes[2] == 'A') { drop_bytes(decoder, 3); return INPUT_UP; }
        if (decoder->bytes[2] == 'B') { drop_bytes(decoder, 3); return INPUT_DOWN; }
        if (decoder->bytes[2] == 'C') { drop_bytes(decoder, 3); return INPUT_RIGHT; }
        if (decoder->bytes[2] == 'D') { drop_bytes(decoder, 3); return INPUT_LEFT; }
        drop_bytes(decoder, 1);
        return INPUT_ESCAPE;
    }
    drop_bytes(decoder, 1);
    if (value == 'q' || value == 'Q') return INPUT_QUIT;
    if (value == '+') return INPUT_PLUS;
    if (value == '-') return INPUT_MINUS;
    if (value == '\t') return INPUT_TAB;
    if (value == ' ') return INPUT_SPACE;
    if (value == '\r' || value == '\n') return INPUT_ENTER;
    if (value == 'l' || value == 'L') return INPUT_LIST;
    if (value == 'h' || value == 'H') return INPUT_HELP;
    if (value == '1') return INPUT_NONE + 101;
    if (value == '2') return INPUT_NONE + 102;
    if (value == '3') return INPUT_NONE + 103;
    if (value == '4') return INPUT_NONE + 104;
    return INPUT_NONE;
}

int input_decoder_feed(InputDecoder *decoder, const unsigned char *bytes, size_t length) {
    size_t copy;
    int key;
    if (decoder == NULL) return INPUT_NONE;
    copy = length;
    if (copy > sizeof(decoder->bytes) - decoder->length) {
        copy = sizeof(decoder->bytes) - decoder->length;
    }
    if (bytes != NULL && copy > 0) {
        memcpy(decoder->bytes + decoder->length, bytes, copy);
        decoder->length += copy;
    }
    key = parse_key(decoder);
    return key;
}

int input_decoder_flush(InputDecoder *decoder) {
    if (decoder == NULL || decoder->length == 0) return INPUT_NONE;
    if (decoder->bytes[0] == 27) {
        decoder->length = 0;
        return INPUT_ESCAPE;
    }
    return parse_key(decoder);
}
