#include "ansiradar80/radar.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#define EARTH_RADIUS_KM 6371.0088
#define NM_PER_KM 0.539956803
#define PI 3.14159265358979323846

static const char *_altitude_text(const Aircraft *aircraft);
static const char *_number_text(double number);
static const char *_heading_text(double heading);
static const char *_age_text(double age);

double radar_distance_nm(double lat1, double lon1, double lat2, double lon2) {
    double p1 = lat1 * PI / 180.0;
    double p2 = lat2 * PI / 180.0;
    double dp = (lat2 - lat1) * PI / 180.0;
    double dl = (lon2 - lon1) * PI / 180.0;
    double a = sin(dp / 2.0) * sin(dp / 2.0) +
               cos(p1) * cos(p2) * sin(dl / 2.0) * sin(dl / 2.0);
    return EARTH_RADIUS_KM * 2.0 * atan2(sqrt(a), sqrt(1.0 - a)) * NM_PER_KM;
}

double radar_bearing_deg(double lat1, double lon1, double lat2, double lon2) {
    double p1 = lat1 * PI / 180.0;
    double p2 = lat2 * PI / 180.0;
    double dl = (lon2 - lon1) * PI / 180.0;
    double y = sin(dl) * cos(p2);
    double x = cos(p1) * sin(p2) - sin(p1) * cos(p2) * cos(dl);
    double bearing = atan2(y, x) * 180.0 / PI;
    return bearing < 0.0 ? bearing + 360.0 : bearing;
}

static size_t order_by_distance(const AircraftList *list, const RadarState *state,
                                size_t *order, size_t capacity) {
    size_t count = 0;
    size_t i;
    if (list == NULL || state == NULL) {
        return 0;
    }
    for (i = 0; i < list->count && count < capacity; ++i) {
        size_t pos = count;
        double distance;
        if (!list->items[i].has_position ||
            (!state->show_ground && list->items[i].on_ground)) {
            continue;
        }
        distance = radar_distance_nm(state->receiver_latitude, state->receiver_longitude,
                                     list->items[i].latitude, list->items[i].longitude);
        if (distance > state->range_nm) {
            continue;
        }
        while (pos > 0) {
            size_t previous = order[pos - 1];
            int comes_after = 0;
            if (state->sort_mode == 1) {
                comes_after = strcmp(list->items[previous].callsign,
                                     list->items[i].callsign) > 0;
            } else if (state->sort_mode == 2) {
                double previous_altitude = list->items[previous].has_altitude
                                               ? list->items[previous].altitude_ft
                                               : -1.0;
                double altitude = list->items[i].has_altitude ? list->items[i].altitude_ft : -1.0;
                comes_after = previous_altitude > altitude;
            } else {
                double previous_distance = radar_distance_nm(
                    state->receiver_latitude, state->receiver_longitude,
                    list->items[previous].latitude, list->items[previous].longitude);
                comes_after = previous_distance > distance;
            }
            if (!comes_after) break;
            order[pos] = previous;
            --pos;
        }
        order[pos] = i;
        ++count;
    }
    return count;
}

static void draw_rings(Screen *screen, int cx, int cy) {
    int ring;
    for (ring = 1; ring <= 3; ++ring) {
        int rx = 11 * ring;
        int ry = 3 * ring;
        int x;
        int y;
        for (x = -rx; x <= rx; ++x) {
            for (y = -ry; y <= ry; ++y) {
                double value = (double)(x * x) / (double)(rx * rx) +
                               (double)(y * y) / (double)(ry * ry);
                if (value > 0.88 && value < 1.12) {
                    screen_put(screen, cx + x, cy + y, '.', 0);
                }
            }
        }
    }
}

static void draw_table(Screen *screen, const AircraftList *list, const RadarState *state,
                       const size_t *order, size_t count) {
    size_t row;
    char line[81];
    screen_text(screen, 2, 20, "CALL     ALT    SPD   HDG DIST AGE", 7);
    for (row = 0; row < count && row < 4; ++row) {
        const Aircraft *aircraft = &list->items[order[row]];
        double distance = radar_distance_nm(state->receiver_latitude, state->receiver_longitude,
                                            aircraft->latitude, aircraft->longitude);
        double bearing = radar_bearing_deg(state->receiver_latitude, state->receiver_longitude,
                                           aircraft->latitude, aircraft->longitude);
        snprintf(line, sizeof(line), "%-8.8s %6s %5s %5s %4.0f %3s",
                 aircraft->callsign[0] ? aircraft->callsign : aircraft->icao,
                 aircraft->has_altitude ? _altitude_text(aircraft) : "-",
                 aircraft->has_speed ? _number_text(aircraft->speed_kt) : "-",
                 aircraft->has_heading ? _heading_text(bearing) : "-",
                 distance,
                 aircraft->has_seen ? _age_text(aircraft->seen_seconds) : "-");
        screen_text(screen, 2, 21 + (int)row, line, row == state->selected ? 15 : 7);
    }
}

/* Small rotating buffers keep the renderer allocation-free. */
static const char *_altitude_text(const Aircraft *aircraft) {
    static char value[4][8];
    static unsigned int slot;
    slot = (slot + 1U) % 4U;
    snprintf(value[slot], sizeof(value[slot]), "%.0f", aircraft->altitude_ft);
    return value[slot];
}

static const char *_number_text(double number) {
    static char value[4][8];
    static unsigned int slot;
    slot = (slot + 1U) % 4U;
    snprintf(value[slot], sizeof(value[slot]), "%.0f", number);
    return value[slot];
}

static const char *_heading_text(double heading) {
    static char value[4][8];
    static unsigned int slot;
    slot = (slot + 1U) % 4U;
    snprintf(value[slot], sizeof(value[slot]), "%03.0f", fmod(heading, 360.0));
    return value[slot];
}

static const char *_age_text(double age) {
    static char value[4][8];
    static unsigned int slot;
    slot = (slot + 1U) % 4U;
    snprintf(value[slot], sizeof(value[slot]), "%.0fs", age);
    return value[slot];
}

void radar_render(Screen *screen, const AircraftList *aircraft,
                  const RadarState *state, const char *utc_text) {
    size_t order[ANSIRADAR80_MAX_AIRCRAFT];
    size_t count;
    size_t i;
    char top[81];
    int cx = 40;
    int cy = 10;
    if (screen == NULL || aircraft == NULL || state == NULL) {
        return;
    }
    screen_clear(screen, ' ', 0);
    snprintf(top, sizeof(top), "ANSIRadar 80        Range:%3.0fnm      Aircraft:%-3lu      UTC:%s",
             state->range_nm, (unsigned long)aircraft->count, utc_text != NULL ? utc_text : "--:--:--");
    screen_text(screen, 0, 0, top, 15);
    if (state->list_mode) {
        screen_text(screen, 30, 2, "AIRCRAFT LIST", 15);
        count = order_by_distance(aircraft, state, order, ANSIRADAR80_MAX_AIRCRAFT);
        draw_table(screen, aircraft, state, order, count);
        screen_text(screen, 2, 18, "L radar  Tab sort  Arrows select  Enter details  H help  Q quit", 7);
        return;
    }
    screen_put(screen, cx, cy - 8, 'N', 15);
    screen_put(screen, cx, cy + 8, 'S', 15);
    screen_put(screen, cx - 35, cy, 'W', 15);
    screen_put(screen, cx + 35, cy, 'E', 15);
    screen_put(screen, cx, cy, '+', 15);
    draw_rings(screen, cx, cy);
    count = order_by_distance(aircraft, state, order, ANSIRADAR80_MAX_AIRCRAFT);
    for (i = 0; i < count; ++i) {
        const Aircraft *item = &aircraft->items[order[i]];
        double distance = radar_distance_nm(state->receiver_latitude, state->receiver_longitude,
                                            item->latitude, item->longitude);
        double bearing = radar_bearing_deg(state->receiver_latitude, state->receiver_longitude,
                                           item->latitude, item->longitude);
        double angle = bearing * PI / 180.0;
        int x = cx + (int)lround(sin(angle) * (distance / state->range_nm) * 34.0);
        int y = cy - (int)lround(cos(angle) * (distance / state->range_nm) * 8.0);
        unsigned char symbol = i == state->selected ? '@' : (item->on_ground ? 'o' : '*');
        screen_put(screen, x, y, symbol, i == state->selected ? 14 : 10);
    }
    draw_table(screen, aircraft, state, order, count);
    screen_text(screen, 2, 18, "Arrows select  Tab sort  Space center  Enter details  L list  H help  Q quit", 7);
}
