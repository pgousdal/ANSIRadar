#include "ansiradar80/charset.h"

static const CharProfile ascii_profile = {'-', '|', '+', '.', '*', 'o', '@', '+'};
static const CharProfile cp437_profile = {'-', '|', '+', '.', '*', 'o', '@', '+'};

const CharProfile *char_profile(int charset) {
    return charset == 1 ? &cp437_profile : &ascii_profile;
}
