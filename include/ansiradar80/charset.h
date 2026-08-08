#ifndef ANSIRADAR80_CHARSET_H
#define ANSIRADAR80_CHARSET_H

typedef struct {
    unsigned char horizontal;
    unsigned char vertical;
    unsigned char corner;
    unsigned char ring;
    unsigned char aircraft;
    unsigned char ground;
    unsigned char selected;
    unsigned char receiver;
} CharProfile;

const CharProfile *char_profile(int charset);

#endif
