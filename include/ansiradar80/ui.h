#ifndef ANSIRADAR80_UI_H
#define ANSIRADAR80_UI_H

#include "aircraft.h"
#include "radar.h"
#include "screen.h"

void ui_draw_help(Screen *screen);
void ui_draw_details(Screen *screen, const AircraftList *list,
                     const RadarState *state);

#endif
