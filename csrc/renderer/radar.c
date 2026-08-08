#include "ansiradar80/radar.h"
#include "ansiradar80/charset.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#define EARTH_RADIUS_KM 6371.0088
#define NM_PER_KM 0.539956803
#define PI 3.14159265358979323846

static const char *number_text(char *buffer, size_t size, double value) {
    snprintf(buffer, size, "%.0f", value);
    return buffer;
}

static const char *heading_text(char *buffer, size_t size, double value) {
    double heading = fmod(value, 360.0);
    if (heading < 0.0) heading += 360.0;
    snprintf(buffer, size, "%03.0f", heading);
    return buffer;
}

static const char *age_text(char *buffer, size_t size, double value) {
    snprintf(buffer, size, "%.0fs", value);
    return buffer;
}

double radar_distance_nm(double lat1, double lon1, double lat2, double lon2) {
    double p1 = lat1 * PI / 180.0;
    double p2 = lat2 * PI / 180.0;
    double dp = (lat2 - lat1) * PI / 180.0;
    double dl = (lon2 - lon1) * PI / 180.0;
    double a = sin(dp / 2.0) * sin(dp / 2.0) +
               cos(p1) * cos(p2) * sin(dl / 2.0) * sin(dl / 2.0);
    if (a < 0.0) a = 0.0;
    if (a > 1.0) a = 1.0;
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

int radar_project(double bearing_deg, double distance_nm, double range_nm,
                  int *x, int *y) {
    double angle;
    if (x == NULL || y == NULL || range_nm <= 0.0 || distance_nm < 0.0 ||
        distance_nm > range_nm) return 0;
    angle = bearing_deg * PI / 180.0;
    *x = 40 + (int)lround(sin(angle) * (distance_nm / range_nm) * 16.0);
    *y = 10 - (int)lround(cos(angle) * (distance_nm / range_nm) * 7.0);
    return *x >= 1 && *x <= 78 && *y >= 2 && *y <= 18;
}

size_t radar_order(const AircraftList *list, const RadarState *state,
                   size_t *order, size_t capacity) {
    size_t count = 0;
    size_t i;
    if (list == NULL || state == NULL || order == NULL) return 0;
    for (i = 0; i < list->count && count < capacity; ++i) {
        size_t pos = count;
        double distance;
        if (!list->items[i].has_position ||
            (!state->show_ground && list->items[i].on_ground)) continue;
        distance = radar_distance_nm(state->receiver_latitude, state->receiver_longitude,
                                     list->items[i].latitude, list->items[i].longitude);
        if (distance > state->range_nm) continue;
        while (pos > 0) {
            size_t previous = order[pos - 1];
            int move = 0;
            if (state->sort_mode == 1) {
                const char *a = list->items[previous].callsign[0]
                                    ? list->items[previous].callsign
                                    : list->items[previous].icao;
                const char *b = list->items[i].callsign[0]
                                    ? list->items[i].callsign
                                    : list->items[i].icao;
                move = strcmp(a, b) > 0;
            } else if (state->sort_mode == 2) {
                double a = list->items[previous].has_altitude
                               ? list->items[previous].altitude_ft
                               : -1.0;
                double b = list->items[i].has_altitude ? list->items[i].altitude_ft : -1.0;
                move = a > b;
            } else {
                double a = radar_distance_nm(state->receiver_latitude,
                                             state->receiver_longitude,
                                             list->items[previous].latitude,
                                             list->items[previous].longitude);
                move = a > distance;
            }
            if (!move) break;
            order[pos] = previous;
            --pos;
        }
        order[pos] = i;
        ++count;
    }
    return count;
}

static void draw_rings(Screen *screen, int cx, int cy, const CharProfile *profile) {
    int ring;
    for (ring = 1; ring <= 3; ++ring) {
        int rx = ring == 3 ? 16 : ring * 5;
        int ry = ring == 3 ? 7 : ring * 2;
        int x;
        int y;
        for (x = -rx; x <= rx; ++x) {
            for (y = -ry; y <= ry; ++y) {
                double value = (double)(x * x) / (double)(rx * rx) +
                               (double)(y * y) / (double)(ry * ry);
                if (value > 0.88 && value < 1.12) {
                    screen_put(screen, cx + x, cy + y, profile->ring, 0);
                }
            }
        }
    }
}

static int collision_wins(const AircraftList *list, size_t candidate,
                          size_t candidate_rank, size_t existing,
                          size_t existing_rank, const RadarState *state) {
    const Aircraft *a = &list->items[candidate];
    const Aircraft *b = &list->items[existing];
    int a_selected = candidate_rank == state->selected;
    int b_selected = existing_rank == state->selected;
    if (a_selected != b_selected) return a_selected;
    if ((a->callsign[0] != '\0') != (b->callsign[0] != '\0')) return a->callsign[0] != '\0';
    {
        double ad = radar_distance_nm(state->receiver_latitude, state->receiver_longitude,
                                      a->latitude, a->longitude);
        double bd = radar_distance_nm(state->receiver_latitude, state->receiver_longitude,
                                      b->latitude, b->longitude);
        if (ad != bd) return ad < bd;
    }
    if (a->has_seen != b->has_seen) return a->has_seen;
    if (a->has_seen && a->seen_seconds != b->seen_seconds) return a->seen_seconds < b->seen_seconds;
    return strcmp(a->icao, b->icao) < 0;
}

static void draw_table(Screen *screen, const AircraftList *list, const RadarState *state,
                       const size_t *order, size_t count) {
    size_t row;
    screen_text(screen, 2, 20, "CALL     ALT    SPD   HDG RNG AGE", 7);
    for (row = 0; row < count && row < 3; ++row) {
        const Aircraft *aircraft = &list->items[order[row]];
        char altitude[8], speed[8], heading[8], age[8], line[81];
        double distance = radar_distance_nm(state->receiver_latitude, state->receiver_longitude,
                                            aircraft->latitude, aircraft->longitude);
        snprintf(line, sizeof(line), "%-8.8s %6s %5s %5s %3.0f %3s",
                 aircraft->callsign[0] ? aircraft->callsign : aircraft->icao,
                 aircraft->has_altitude ? number_text(altitude, sizeof(altitude), aircraft->altitude_ft) : "-",
                 aircraft->has_speed ? number_text(speed, sizeof(speed), aircraft->speed_kt) : "-",
                 aircraft->has_heading ? heading_text(heading, sizeof(heading), aircraft->heading_deg) : "-",
                 distance,
                 aircraft->has_seen ? age_text(age, sizeof(age), aircraft->seen_seconds) : "-");
        screen_text(screen, 2, 21 + (int)row, line, row == state->selected ? 15 : 7);
    }
}

void radar_render(Screen *screen, const AircraftList *aircraft,
                  const RadarState *state, const char *utc_text) {
    size_t order[ANSIRADAR80_MAX_AIRCRAFT];
    size_t count;
    size_t rank;
    char top[81];
    int occupied[ANSIRADAR80_SCREEN_WIDTH * ANSIRADAR80_SCREEN_HEIGHT];
    int cx = 40;
    int cy = 10;
    const CharProfile *profile;
    if (screen == NULL || aircraft == NULL || state == NULL) return;
    profile = char_profile(state->charset);
    screen_clear(screen, ' ', 0);
    snprintf(top, sizeof(top), "ANSIRadar 80        Range:%3.0fnm      Aircraft:%-3lu      UTC:%s",
             state->range_nm, (unsigned long)aircraft->count,
             utc_text != NULL ? utc_text : "--:--:--");
    screen_text(screen, 0, 0, top, 15);
    count = radar_order(aircraft, state, order, ANSIRADAR80_MAX_AIRCRAFT);
    if (state->list_mode) {
        screen_text(screen, 30, 2, "AIRCRAFT LIST", 15);
        draw_table(screen, aircraft, state, order, count);
        screen_text(screen, 2, 19, state->source_status[0] ? state->source_status : "OK", 7);
        screen_text(screen, 2, 24, "L radar Tab sort Arrows select Enter details H help Q quit", 7);
        return;
    }
    screen_put(screen, cx, cy - 8, 'N', 15);
    screen_put(screen, cx, cy + 8, 'S', 15);
    screen_put(screen, cx - 35, cy, 'W', 15);
    screen_put(screen, cx + 35, cy, 'E', 15);
    screen_put(screen, cx, cy, profile->receiver, 15);
    draw_rings(screen, cx, cy, profile);
    for (rank = 0; rank < sizeof(occupied) / sizeof(occupied[0]); ++rank) occupied[rank] = -1;
    for (rank = 0; rank < count; ++rank) {
        const Aircraft *item = &aircraft->items[order[rank]];
        double distance = radar_distance_nm(state->receiver_latitude, state->receiver_longitude,
                                            item->latitude, item->longitude);
        double bearing = radar_bearing_deg(state->receiver_latitude, state->receiver_longitude,
                                           item->latitude, item->longitude);
        int x;
        int y;
        int cell;
        if (!radar_project(bearing, distance, state->range_nm, &x, &y)) continue;
        cell = y * ANSIRADAR80_SCREEN_WIDTH + x;
        if (occupied[cell] < 0 || collision_wins(aircraft, order[rank], rank,
                                                  order[(size_t)occupied[cell]],
                                                  (size_t)occupied[cell], state)) {
            occupied[cell] = (int)rank;
        }
    }
    for (rank = 0; rank < count; ++rank) {
        const Aircraft *item = &aircraft->items[order[rank]];
        double distance = radar_distance_nm(state->receiver_latitude, state->receiver_longitude,
                                            item->latitude, item->longitude);
        double bearing = radar_bearing_deg(state->receiver_latitude, state->receiver_longitude,
                                           item->latitude, item->longitude);
        int x;
        int y;
        unsigned char symbol;
        if (!radar_project(bearing, distance, state->range_nm, &x, &y) ||
            occupied[y * ANSIRADAR80_SCREEN_WIDTH + x] != (int)rank) continue;
        symbol = rank == state->selected ? profile->selected
                                         : item->on_ground ? profile->ground : profile->aircraft;
        screen_put(screen, x, y, symbol, rank == state->selected ? 14 : 10);
    }
    draw_table(screen, aircraft, state, order, count);
    screen_text(screen, 2, 19, state->source_status[0] ? state->source_status : "OK", 7);
    screen_text(screen, 2, 24, "Arrows select Tab sort Space center Enter details L list H help Q quit", 7);
}
