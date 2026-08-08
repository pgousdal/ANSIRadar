#ifndef ANSIRADAR80_AIRCRAFT_H
#define ANSIRADAR80_AIRCRAFT_H

#include <stddef.h>

#define ANSIRADAR80_MAX_AIRCRAFT 256
#define ANSIRADAR80_CALLSIGN_LEN 16

typedef struct {
    char icao[7];
    char callsign[ANSIRADAR80_CALLSIGN_LEN];
    char squawk[8];
    double latitude;
    double longitude;
    double altitude_ft;
    double speed_kt;
    double heading_deg;
    double vertical_fpm;
    double seen_seconds;
    int has_position;
    int has_altitude;
    int has_speed;
    int has_heading;
    int has_vertical;
    int has_seen;
    int has_squawk;
    int on_ground;
} Aircraft;

typedef struct {
    Aircraft items[ANSIRADAR80_MAX_AIRCRAFT];
    size_t count;
    unsigned long messages;
} AircraftList;

void aircraft_list_clear(AircraftList *list);
int aircraft_list_add(AircraftList *list, const Aircraft *aircraft);
void aircraft_normalize(Aircraft *aircraft);

#endif
