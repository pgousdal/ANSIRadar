#include "ansiradar80/provider.h"

#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_SOURCE_BYTES (4U * 1024U * 1024U)
#define MAX_REPLAY_LINES 10000U

typedef struct {
    char *path;
} FileContext;

typedef struct {
    char **lines;
    size_t count;
    size_t cursor;
} ReplayContext;

static char *duplicate_string(const char *value) {
    size_t length;
    char *copy;
    if (value == NULL) return NULL;
    length = strlen(value);
    copy = (char *)malloc(length + 1U);
    if (copy != NULL) memcpy(copy, value, length + 1U);
    return copy;
}

static int equals_ignore_case(const char *left, const char *right) {
    while (*left != '\0' && *right != '\0') {
        if (tolower((unsigned char)*left) != tolower((unsigned char)*right)) return 0;
        ++left;
        ++right;
    }
    return *left == *right;
}

static void set_error(char *error, size_t size, const char *message) {
    if (error != NULL && size > 0) {
        snprintf(error, size, "%s", message != NULL ? message : "provider error");
    }
}

static char *read_bounded_file(const char *path, char *error, size_t error_size) {
    FILE *file;
    long length;
    char *data;
    size_t read_count;
    file = fopen(path, "rb");
    if (file == NULL) {
        snprintf(error, error_size, "cannot open %s: %s", path, strerror(errno));
        return NULL;
    }
    if (fseek(file, 0, SEEK_END) != 0 || (length = ftell(file)) < 0 ||
        (unsigned long)length > MAX_SOURCE_BYTES || fseek(file, 0, SEEK_SET) != 0) {
        fclose(file);
        set_error(error, error_size, "source file is too large or not seekable");
        return NULL;
    }
    data = (char *)malloc((size_t)length + 1U);
    if (data == NULL) {
        fclose(file);
        set_error(error, error_size, "out of memory reading source");
        return NULL;
    }
    read_count = fread(data, 1, (size_t)length, file);
    fclose(file);
    if (read_count != (size_t)length) {
        free(data);
        set_error(error, error_size, "short source read");
        return NULL;
    }
    data[read_count] = '\0';
    return data;
}

static const char *find_key(const char *object, const char *key) {
    char needle[64];
    snprintf(needle, sizeof(needle), "\"%s\"", key);
    return strstr(object, needle);
}

static const char *after_colon(const char *field) {
    const char *colon = strchr(field, ':');
    if (colon == NULL) {
        return NULL;
    }
    ++colon;
    while (*colon != '\0' && isspace((unsigned char)*colon)) {
        ++colon;
    }
    return colon;
}

static int json_number(const char *object, const char *key, double *value) {
    const char *field = find_key(object, key);
    const char *start;
    char *end;
    if (field == NULL || (start = after_colon(field)) == NULL || *start == 'n') {
        return 0;
    }
    *value = strtod(start, &end);
    return end != start;
}

static int json_string(const char *object, const char *key, char *output, size_t size) {
    const char *field = find_key(object, key);
    const char *start;
    size_t used = 0;
    if (field == NULL || (start = after_colon(field)) == NULL || *start != '"' || size == 0) {
        return 0;
    }
    ++start;
    while (*start != '\0' && *start != '"' && used + 1U < size) {
        if (*start == '\\' && start[1] != '\0') {
            ++start;
        }
        output[used++] = *start++;
    }
    output[used] = '\0';
    return 1;
}

static const char *object_end(const char *object) {
    int depth = 0;
    int quoted = 0;
    int escaped = 0;
    const char *cursor;
    for (cursor = object; *cursor != '\0'; ++cursor) {
        if (quoted) {
            if (escaped) {
                escaped = 0;
            } else if (*cursor == '\\') {
                escaped = 1;
            } else if (*cursor == '"') {
                quoted = 0;
            }
            continue;
        }
        if (*cursor == '"') {
            quoted = 1;
        } else if (*cursor == '{') {
            ++depth;
        } else if (*cursor == '}' && --depth == 0) {
            return cursor;
        }
    }
    return NULL;
}

static void parse_aircraft_object(const char *object, Aircraft *aircraft) {
    double number;
    char altitude[32];
    memset(aircraft, 0, sizeof(*aircraft));
    if (!json_string(object, "hex", aircraft->icao, sizeof(aircraft->icao))) {
        return;
    }
    json_string(object, "flight", aircraft->callsign, sizeof(aircraft->callsign));
    if (json_string(object, "squawk", aircraft->squawk, sizeof(aircraft->squawk))) {
        aircraft->has_squawk = 1;
    }
    if (json_number(object, "lat", &aircraft->latitude) &&
        json_number(object, "lon", &aircraft->longitude) &&
        aircraft->latitude >= -90.0 && aircraft->latitude <= 90.0 &&
        aircraft->longitude >= -180.0 && aircraft->longitude <= 180.0) {
        aircraft->has_position = 1;
    }
    if (json_string(object, "alt_baro", altitude, sizeof(altitude)) &&
        equals_ignore_case(altitude, "ground")) {
        aircraft->on_ground = 1;
    } else if (json_number(object, "alt_baro", &number) ||
               json_number(object, "alt_geom", &number)) {
        aircraft->altitude_ft = number;
        aircraft->has_altitude = 1;
    }
    if (json_number(object, "gs", &number)) {
        aircraft->speed_kt = number;
        aircraft->has_speed = 1;
    }
    if (json_number(object, "track", &number)) {
        aircraft->heading_deg = number;
        aircraft->has_heading = 1;
    }
    if (json_number(object, "baro_rate", &number) || json_number(object, "geom_rate", &number)) {
        aircraft->vertical_fpm = number;
        aircraft->has_vertical = 1;
    }
    if (json_number(object, "seen_pos", &number) || json_number(object, "seen", &number)) {
        aircraft->seen_seconds = number;
        aircraft->has_seen = 1;
    }
    aircraft_normalize(aircraft);
}

static int parse_readsb_json(const char *data, AircraftList *list,
                             char *error, size_t error_size) {
    const char *array = strstr(data, "\"aircraft\"");
    const char *cursor;
    if (array == NULL || (array = strchr(array, '[')) == NULL) {
        set_error(error, error_size, "JSON document has no aircraft array");
        return 0;
    }
    cursor = array + 1;
    aircraft_list_clear(list);
    while (*cursor != '\0' && *cursor != ']') {
        const char *end;
        Aircraft aircraft;
        while (*cursor != '\0' && (isspace((unsigned char)*cursor) || *cursor == ',')) {
            ++cursor;
        }
        if (*cursor == ']') {
            break;
        }
        if (*cursor != '{' || (end = object_end(cursor)) == NULL) {
            set_error(error, error_size, "malformed aircraft object");
            return 0;
        }
        parse_aircraft_object(cursor, &aircraft);
        if (strlen(aircraft.icao) == 6) {
            aircraft_list_add(list, &aircraft);
        }
        cursor = end + 1;
    }
    return 1;
}

static int file_poll(Provider *provider, AircraftList *list, char *error, size_t error_size) {
    FileContext *context = (FileContext *)provider->context;
    char *data = read_bounded_file(context->path, error, error_size);
    int result;
    if (data == NULL) {
        return 0;
    }
    result = parse_readsb_json(data, list, error, error_size);
    free(data);
    return result;
}

static void file_close(Provider *provider) {
    FileContext *context = (FileContext *)provider->context;
    if (context != NULL) {
        free(context->path);
        free(context);
    }
    provider->context = NULL;
}

static int create_file_provider(Provider *provider, const char *path,
                                const char *name, char *error, size_t error_size) {
    FileContext *context;
    if (provider == NULL || path == NULL || path[0] == '\0') {
        set_error(error, error_size, "provider path is required");
        return 0;
    }
    context = (FileContext *)calloc(1, sizeof(*context));
    if (context == NULL || (context->path = duplicate_string(path)) == NULL) {
        free(context);
        set_error(error, error_size, "out of memory creating provider");
        return 0;
    }
    provider->context = context;
    provider->poll = file_poll;
    provider->close = file_close;
    provider->name = name;
    return 1;
}

int provider_readsb_file_create(Provider *provider, const char *path,
                                char *error, size_t error_size) {
    return create_file_provider(provider, path, "readsb-json", error, error_size);
}

int provider_dump1090_file_create(Provider *provider, const char *path,
                                  char *error, size_t error_size) {
    return create_file_provider(provider, path, "dump1090-json", error, error_size);
}

static int replay_poll(Provider *provider, AircraftList *list, char *error, size_t error_size) {
    ReplayContext *context = (ReplayContext *)provider->context;
    char *line;
    double timestamp;
    unsigned long sequence = 0;
    aircraft_list_clear(list);
    while (context->cursor < context->count) {
        char *save;
        line = context->lines[context->cursor++];
        if (line[0] == '\0' || !isdigit((unsigned char)line[0])) {
            continue;
        }
        timestamp = strtod(line, &save);
        if (save == line) {
            continue;
        }
        while (*save == ',' || isspace((unsigned char)*save)) {
            ++save;
        }
        {
            char *token = strtok(save, ",\r\n");
            Aircraft aircraft;
            memset(&aircraft, 0, sizeof(aircraft));
            if (token == NULL) {
                continue;
            }
            snprintf(aircraft.icao, sizeof(aircraft.icao), "%s", token);
            token = strtok(NULL, ",\r\n");
            if (token != NULL) snprintf(aircraft.callsign, sizeof(aircraft.callsign), "%s", token);
            token = strtok(NULL, ",\r\n");
            if (token != NULL) aircraft.latitude = strtod(token, NULL);
            token = strtok(NULL, ",\r\n");
            if (token != NULL) {
                aircraft.longitude = strtod(token, NULL);
                aircraft.has_position = aircraft.latitude >= -90.0 && aircraft.latitude <= 90.0 &&
                                        aircraft.longitude >= -180.0 && aircraft.longitude <= 180.0;
            }
            token = strtok(NULL, ",\r\n");
            if (token != NULL) { aircraft.altitude_ft = strtod(token, NULL); aircraft.has_altitude = 1; }
            token = strtok(NULL, ",\r\n");
            if (token != NULL) { aircraft.speed_kt = strtod(token, NULL); aircraft.has_speed = 1; }
            token = strtok(NULL, ",\r\n");
            if (token != NULL) { aircraft.heading_deg = strtod(token, NULL); aircraft.has_heading = 1; }
            token = strtok(NULL, ",\r\n");
            if (token != NULL) { aircraft.vertical_fpm = strtod(token, NULL); aircraft.has_vertical = 1; }
            token = strtok(NULL, ",\r\n");
            if (token != NULL) { aircraft.seen_seconds = strtod(token, NULL); aircraft.has_seen = 1; }
            aircraft_normalize(&aircraft);
            aircraft_list_add(list, &aircraft);
            ++sequence;
        }
        (void)timestamp;
        if (sequence > 0) {
            return 1;
        }
    }
    set_error(error, error_size, "replay exhausted");
    return 0;
}

static void replay_close(Provider *provider) {
    ReplayContext *context = (ReplayContext *)provider->context;
    size_t i;
    if (context != NULL) {
        for (i = 0; i < context->count; ++i) free(context->lines[i]);
        free(context->lines);
        free(context);
    }
    provider->context = NULL;
}

int provider_replay_csv_create(Provider *provider, const char *path,
                               char *error, size_t error_size) {
    FILE *file;
    ReplayContext *context;
    char line[1024];
    if (provider == NULL || path == NULL) {
        set_error(error, error_size, "replay path is required");
        return 0;
    }
    file = fopen(path, "r");
    if (file == NULL) {
        snprintf(error, error_size, "cannot open replay: %s", strerror(errno));
        return 0;
    }
    context = (ReplayContext *)calloc(1, sizeof(*context));
    while (context != NULL && context->count < MAX_REPLAY_LINES && fgets(line, sizeof(line), file) != NULL) {
        char *copy = duplicate_string(line);
        char **grown;
        if (copy == NULL) break;
        grown = (char **)realloc(context->lines, (context->count + 1U) * sizeof(*grown));
        if (grown == NULL) { free(copy); break; }
        context->lines = grown;
        context->lines[context->count++] = copy;
    }
    fclose(file);
    if (context == NULL || context->count == 0) {
        free(context);
        set_error(error, error_size, "empty or invalid replay");
        return 0;
    }
    provider->context = context;
    provider->poll = replay_poll;
    provider->close = replay_close;
    provider->name = "csv-replay";
    return 1;
}

void provider_destroy(Provider *provider) {
    if (provider != NULL && provider->close != NULL) {
        provider->close(provider);
    }
}
