#include "ansiradar80/aircraft.h"

#include <ctype.h>
#include <string.h>

void aircraft_list_clear(AircraftList *list) {
    if (list != NULL) {
        memset(list, 0, sizeof(*list));
    }
}

int aircraft_list_add(AircraftList *list, const Aircraft *aircraft) {
    if (list == NULL || aircraft == NULL ||
        list->count >= ANSIRADAR80_MAX_AIRCRAFT) {
        return 0;
    }
    list->items[list->count++] = *aircraft;
    return 1;
}

void aircraft_normalize(Aircraft *aircraft) {
    size_t i;
    if (aircraft == NULL) {
        return;
    }
    for (i = 0; i < sizeof(aircraft->icao) - 1 && aircraft->icao[i] != '\0'; ++i) {
        aircraft->icao[i] = (char)toupper((unsigned char)aircraft->icao[i]);
    }
    for (i = 0; i < sizeof(aircraft->callsign) - 1 && aircraft->callsign[i] != '\0'; ++i) {
        if ((unsigned char)aircraft->callsign[i] < 32 ||
            (unsigned char)aircraft->callsign[i] == 127) {
            aircraft->callsign[i] = ' ';
        }
    }
}
