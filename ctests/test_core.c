#include "ansiradar80/ansi.h"
#include "ansiradar80/input.h"
#include "ansiradar80/provider.h"
#include "ansiradar80/radar.h"
#include "ansiradar80/screen.h"
#include "ansiradar80/charset.h"
#include "ansiradar80/ui.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static void assert_ansi_bounds(const char *output) {
    const char *cursor = output;
    while (*cursor != '\0') {
        if (cursor[0] == '\033' && cursor[1] == '[') {
            int row;
            int column;
            if (sscanf(cursor, "\033[%d;%dH", &row, &column) == 2) {
                assert(row >= 1 && row <= 25);
                assert(column >= 1 && column <= 80);
            }
        }
        ++cursor;
    }
    assert(strchr(output, '\n') == NULL);
}

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
    int x;
    int y;
    size_t order[ANSIRADAR80_MAX_AIRCRAFT];
    assert(radar_distance_nm(58.0, 6.0, 58.0, 6.0) == 0.0);
    assert(radar_bearing_deg(58.0, 6.0, 59.0, 6.0) == 0.0);
    assert(radar_project(0.0, 100.0, 100.0, &x, &y) && x == 40 && y == 3);
    assert(radar_project(90.0, 100.0, 100.0, &x, &y) && x == 56 && y == 10);
    assert(radar_project(180.0, 100.0, 100.0, &x, &y) && x == 40 && y == 17);
    assert(radar_project(270.0, 100.0, 100.0, &x, &y) && x == 24 && y == 10);
    assert(radar_project(45.0, 100.0, 100.0, &x, &y) && x == 51 && y == 5);
    assert(radar_project(135.0, 100.0, 100.0, &x, &y) && x == 51 && y == 15);
    assert(radar_project(225.0, 100.0, 100.0, &x, &y) && x == 29 && y == 15);
    assert(radar_project(315.0, 100.0, 100.0, &x, &y) && x == 29 && y == 5);
    assert(!radar_project(0.0, 100.1, 100.0, &x, &y));
    screen_clear(&first, ' ', 0);
    screen_text(&first, 0, 0, "HELLO", 7);
    result = ansi_full(&first, output, sizeof(output), 0);
    assert(result > 0 && strchr(output, 'H') != NULL && strchr(output, 'O') != NULL);
    assert_ansi_bounds(output);
    second = first;
    screen_put(&second, 0, 0, 'J', 7);
    result = ansi_diff(&second, &first, output, sizeof(output), 0);
    assert(result > 0 && strchr(output, 'J') != NULL);
    input_decoder_init(&decoder);
    assert(input_decoder_feed(&decoder, (const unsigned char *)"j", 1) == INPUT_NONE);
    assert(input_decoder_feed(&decoder, (const unsigned char *)"\033[", 2) == INPUT_NONE);
    assert(input_decoder_feed(&decoder, (const unsigned char *)"A", 1) == INPUT_UP);
    input_decoder_init(&decoder);
    assert(input_decoder_feed(&decoder, (const unsigned char *)"+", 1) == INPUT_PLUS);
    assert(input_decoder_feed(&decoder, (const unsigned char *)"-", 1) == INPUT_MINUS);
    assert(input_decoder_feed(&decoder, (const unsigned char *)"\t", 1) == INPUT_TAB);
    assert(input_decoder_feed(&decoder, (const unsigned char *)" ", 1) == INPUT_SPACE);
    input_decoder_init(&decoder);
    assert(input_decoder_feed(&decoder, (const unsigned char *)"\033", 1) == INPUT_NONE);
    assert(input_decoder_feed(&decoder, (const unsigned char *)"[", 1) == INPUT_NONE);
    assert(input_decoder_feed(&decoder, (const unsigned char *)"A", 1) == INPUT_UP);
    input_decoder_init(&decoder);
    assert(input_decoder_feed(&decoder, (const unsigned char *)"jp1", 3) == INPUT_NONE);
    assert(input_decoder_feed(&decoder, NULL, 0) == INPUT_NONE);
    assert(input_decoder_feed(&decoder, NULL, 0) == 101);
    input_decoder_init(&decoder);
    assert(input_decoder_feed(&decoder, (const unsigned char *)"\033", 1) == INPUT_NONE);
    assert(input_decoder_timeout(&decoder) == INPUT_NONE);
    assert(input_decoder_timeout(&decoder) == INPUT_ESCAPE);
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
    state.charset = 1;
    aircraft_list_clear(&list);
    radar_render(&first, &list, &state, "12:34:56");
    assert(first.cells[0].ch == 'A');
    for (y = 0; y < first.height; ++y) {
        for (x = 0; x < first.width; ++x) {
            assert(x >= 0 && x < 80 && y >= 0 && y < 25);
        }
    }
    assert(char_profile(0)->aircraft == '*');
    assert(char_profile(1)->ground == 'o');
    memset(&list, 0, sizeof(list));
    strcpy(list.items[0].icao, "AAA001");
    strcpy(list.items[1].icao, "AAA002");
    strcpy(list.items[1].callsign, "CALLED");
    list.items[0].latitude = list.items[1].latitude = 58.67;
    list.items[0].longitude = list.items[1].longitude = 6.28;
    list.items[0].has_position = list.items[1].has_position = 1;
    list.count = 2;
    state.selected = 1;
    assert(radar_order(&list, &state, order, 2) == 2);
    radar_render(&second, &list, &state, "12:34:56");
    assert(radar_project(radar_bearing_deg(state.receiver_latitude, state.receiver_longitude,
                                           58.67, 6.28),
                         radar_distance_nm(state.receiver_latitude, state.receiver_longitude,
                                           58.67, 6.28), state.range_nm, &x, &y));
    assert(screen_get(&second, x, y).ch == '@');
    strcpy(list.items[0].callsign, "THIS-CALLSIGN-IS-LONG");
    radar_render(&second, &list, &state, "12:34:56");
    ui_draw_help(&second);
    ui_draw_details(&second, &list, &state);
    result = ansi_full(&second, output, sizeof(output), 0);
    assert(result > 0 && result < (int)sizeof(output));
    assert_ansi_bounds(output);
    assert(ansi_diff(&second, &first, output, sizeof(output), 0) < result);
    memset(&provider, 0, sizeof(provider));
    assert(provider_readsb_file_create(&provider, "fixtures80/missing.json", error, sizeof(error)));
    assert(!provider.poll(&provider, &list, error, sizeof(error)));
    provider_destroy(&provider);
    return 0;
}
