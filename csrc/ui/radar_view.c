#include "ansiradar80/app.h"
#include "ansiradar80/ansi.h"
#include "ansiradar80/input.h"
#include "ansiradar80/radar.h"

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/select.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

static void utc_now(char *output, size_t size) {
    time_t now = time(NULL);
    struct tm *value = gmtime(&now);
    if (value == NULL) {
        snprintf(output, size, "--:--:--");
        return;
    }
    strftime(output, size, "%H:%M:%S", value);
}

static void overlay_box(Screen *screen, int x, int y, int width, int height) {
    int ix;
    int iy;
    for (ix = 0; ix < width; ++ix) {
        screen_put(screen, x + ix, y, ix == 0 ? '+' : (ix == width - 1 ? '+' : '-'), 15);
        screen_put(screen, x + ix, y + height - 1, ix == 0 ? '+' : (ix == width - 1 ? '+' : '-'), 15);
    }
    for (iy = 1; iy < height - 1; ++iy) {
        screen_put(screen, x, y + iy, '|', 15);
        screen_put(screen, x + width - 1, y + iy, '|', 15);
    }
}

static void draw_help(Screen *screen) {
    overlay_box(screen, 10, 4, 60, 15);
    screen_text(screen, 26, 5, "ANSIRadar 80 controls", 15);
    screen_text(screen, 14, 7, "Arrows select   +/- zoom   Tab sort", 7);
    screen_text(screen, 14, 8, "Space center   Enter details   L list", 7);
    screen_text(screen, 14, 9, "H help         Esc closes popup", 7);
    screen_text(screen, 14, 10, "Q quit", 7);
}

static void draw_details(Screen *screen, const AircraftList *list, const RadarState *state) {
    const Aircraft *aircraft;
    char line[64];
    if (list->count == 0 || state->selected >= list->count) return;
    aircraft = &list->items[state->selected];
    overlay_box(screen, 26, 4, 30, 14);
    screen_text(screen, 29, 5, aircraft->callsign[0] ? aircraft->callsign : aircraft->icao, 15);
    snprintf(line, sizeof(line), "Alt: %.0f ft", aircraft->has_altitude ? aircraft->altitude_ft : 0.0);
    screen_text(screen, 29, 7, line, 7);
    snprintf(line, sizeof(line), "Speed: %.0f kt", aircraft->has_speed ? aircraft->speed_kt : 0.0);
    screen_text(screen, 29, 8, line, 7);
    snprintf(line, sizeof(line), "Heading: %.0f", aircraft->has_heading ? aircraft->heading_deg : 0.0);
    screen_text(screen, 29, 9, line, 7);
    snprintf(line, sizeof(line), "Vertical: %.0f ft/min", aircraft->has_vertical ? aircraft->vertical_fpm : 0.0);
    screen_text(screen, 29, 10, line, 7);
    screen_text(screen, 29, 12, "ICAO:", 7);
    screen_text(screen, 35, 12, aircraft->icao, 7);
    screen_text(screen, 29, 14, "ESC closes", 15);
}

static int read_key(int fd, InputDecoder *decoder, double timeout) {
    unsigned char bytes[64];
    fd_set read_set;
    struct timeval wait;
    int result;
    FD_ZERO(&read_set);
    FD_SET(fd, &read_set);
    wait.tv_sec = (long)timeout;
    wait.tv_usec = (long)((timeout - (double)wait.tv_sec) * 1000000.0);
    result = select(fd + 1, &read_set, NULL, NULL, &wait);
    if (result <= 0) {
        return input_decoder_flush(decoder);
    }
    result = (int)read(fd, bytes, sizeof(bytes));
    if (result <= 0) return INPUT_QUIT;
    return input_decoder_feed(decoder, bytes, (size_t)result);
}

int app_run(const AppConfig *config, Provider *provider) {
    Screen current;
    Screen previous;
    AircraftList aircraft;
    RadarState state;
    InputDecoder decoder;
    char output[128 * 1024];
    char error[256];
    char utc[16];
    int has_previous = 0;
    int details = 0;
    int help = 0;
    int running = 1;
    struct termios original;
    int raw_terminal = 0;
    if (config == NULL || provider == NULL) return 2;
    memset(&state, 0, sizeof(state));
    state.receiver_latitude = config->receiver_latitude;
    state.receiver_longitude = config->receiver_longitude;
    state.range_nm = config->range_nm > 0.0 ? config->range_nm : 100.0;
    state.show_ground = 1;
    aircraft_list_clear(&aircraft);
    input_decoder_init(&decoder);
    if (config->once) {
        if (!provider->poll(provider, &aircraft, error, sizeof(error))) return 3;
    } else if (isatty(STDIN_FILENO) && tcgetattr(STDIN_FILENO, &original) == 0) {
        struct termios raw = original;
        raw.c_lflag &= (tcflag_t)~(ICANON | ECHO);
        raw.c_cc[VMIN] = 0;
        raw.c_cc[VTIME] = 1;
        tcsetattr(STDIN_FILENO, TCSANOW, &raw);
        raw_terminal = 1;
    }
    while (running) {
        if (!config->once && !provider->poll(provider, &aircraft, error, sizeof(error))) {
            /* Keep the last good list during source outages. */
        }
        utc_now(utc, sizeof(utc));
        radar_render(&current, &aircraft, &state, utc);
        if (details) draw_details(&current, &aircraft, &state);
        if (help) draw_help(&current);
        if (config->once) {
            int length = ansi_full(&current, output, sizeof(output), config->color);
            if (length > 0) fwrite(output, 1, (size_t)length, stdout);
            running = 0;
        } else {
            int length = has_previous ? ansi_diff(&current, &previous, output, sizeof(output), config->color)
                                      : ansi_full(&current, output, sizeof(output), config->color);
            if (length > 0) fwrite(output, 1, (size_t)length, stdout);
            fflush(stdout);
            previous = current;
            has_previous = 1;
            switch (read_key(STDIN_FILENO, &decoder, 0.10)) {
                case INPUT_QUIT: running = 0; break;
                case INPUT_UP: if (state.selected > 0) --state.selected; break;
                case INPUT_DOWN: if (state.selected + 1 < aircraft.count) ++state.selected; break;
                case INPUT_PLUS: state.range_nm = state.range_nm > 5.0 ? state.range_nm / 2.0 : 5.0; break;
                case INPUT_MINUS: state.range_nm = state.range_nm < 500.0 ? state.range_nm * 2.0 : 500.0; break;
                case INPUT_TAB: state.sort_mode = (state.sort_mode + 1) % 3; break;
                case INPUT_SPACE: break; /* radar is always centered on receiver */
                case INPUT_LIST: state.list_mode = !state.list_mode; break;
                case INPUT_HELP: help = !help; break;
                case INPUT_ENTER: details = 1; break;
                case INPUT_ESCAPE: details = 0; help = 0; break;
                case 101: state.range_nm = 25.0; break;
                case 102: state.range_nm = 50.0; break;
                case 103: state.range_nm = 100.0; break;
                case 104: state.range_nm = 200.0; break;
                default: break;
            }
        }
    }
    if (raw_terminal) tcsetattr(STDIN_FILENO, TCSANOW, &original);
    ansi_stop(output, sizeof(output));
    fwrite(output, 1, strlen(output), stdout);
    fflush(stdout);
    return 0;
}
