#ifndef ANSIRADAR80_RADAR_H
#define ANSIRADAR80_RADAR_H

#include "aircraft.h"
#include "screen.h"

typedef struct {
    double receiver_latitude;
    double receiver_longitude;
    double range_nm;
    size_t selected;
    int list_mode;
    int show_ground;
    int sort_mode;
    int charset;
    char source_status[16];
} RadarState;

double radar_distance_nm(double lat1, double lon1, double lat2, double lon2);
double radar_bearing_deg(double lat1, double lon1, double lat2, double lon2);
int radar_project(double bearing_deg, double distance_nm, double range_nm,
                  int *x, int *y);
void radar_render(Screen *screen, const AircraftList *aircraft,
                  const RadarState *state, const char *utc_text);
size_t radar_order(const AircraftList *list, const RadarState *state,
                   size_t *order, size_t capacity);

#endif
