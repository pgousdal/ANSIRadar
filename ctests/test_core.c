#include "ansiradar80/ansi.h"
#include "ansiradar80/input.h"
#include "ansiradar80/provider.h"
#include "ansiradar80/radar.h"
#include "ansiradar80/screen.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
    Screen first;
    Screen second;
    InputDecoder decoder;
    AircraftList list;
    Provider provider;
    RadarState state;
    char output[65536];
    char error[256];
    int result;
    assert(radar_distance_nm(58.0, 6.0, 58.0, 6.0) == 0.0);
    assert(radar_bearing_deg(58.0, 6.0, 59.0, 6.0) == 0.0);
    screen_clear(&first, ' ', 0);
    screen_text(&first, 0, 0, "HELLO", 7);
    result = ansi_full(&first, output, sizeof(output), 0);
    assert(result > 0 && strchr(output, 'H') != NULL && strchr(output, 'O') != NULL);
    second = first;
    screen_put(&second, 0, 0, 'J', 7);
    result = ansi_diff(&second, &first, output, sizeof(output), 0);
    assert(result > 0 && strchr(output, 'J') != NULL);
    input_decoder_init(&decoder);
    assert(input_decoder_feed(&decoder, (const unsigned char *)"j", 1) == INPUT_NONE);
    assert(input_decoder_feed(&decoder, (const unsigned char *)"\033[", 2) == INPUT_NONE);
    assert(input_decoder_feed(&decoder, (const unsigned char *)"A", 1) == INPUT_UP);
    memset(&provider, 0, sizeof(provider));
    if (argc > 1) {
        assert(provider_readsb_file_create(&provider, argv[1], error, sizeof(error)));
        assert(provider.poll(&provider, &list, error, sizeof(error)));
        assert(list.count >= 1);
        assert(strcmp(list.items[0].icao, "478ABC") == 0);
        provider_destroy(&provider);
    }
    memset(&state, 0, sizeof(state));
    state.receiver_latitude = 58.3405;
    state.receiver_longitude = 6.2812;
    state.range_nm = 100.0;
    state.show_ground = 1;
    aircraft_list_clear(&list);
    radar_render(&first, &list, &state, "12:34:56");
    assert(first.cells[0].ch == 'A');
    return 0;
}
