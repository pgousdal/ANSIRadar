#ifndef ANSIRADAR80_PROVIDER_H
#define ANSIRADAR80_PROVIDER_H

#include <stddef.h>

#include "aircraft.h"

typedef struct Provider Provider;
typedef int (*ProviderPoll)(Provider *, AircraftList *, char *, size_t);
typedef void (*ProviderClose)(Provider *);

struct Provider {
    void *context;
    ProviderPoll poll;
    ProviderClose close;
    const char *name;
};

int provider_readsb_file_create(Provider *provider, const char *path,
                                char *error, size_t error_size);
int provider_dump1090_file_create(Provider *provider, const char *path,
                                  char *error, size_t error_size);
int provider_replay_csv_create(Provider *provider, const char *path,
                               char *error, size_t error_size);
void provider_destroy(Provider *provider);

#endif
