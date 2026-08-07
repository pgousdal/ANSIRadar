#include "ansiradar80/app.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void usage(const char *program) {
    printf("Usage: %s [options]\n", program);
    puts("  --source readsb|dump1090|replay");
    puts("  --file PATH              JSON snapshot or CSV replay");
    puts("  --receiver-lat FLOAT     receiver latitude");
    puts("  --receiver-lon FLOAT     receiver longitude");
    puts("  --range NM               radar range (default 100)");
    puts("  --once                   render one deterministic frame");
    puts("  --color always|never     ANSI color policy");
    puts("  --width 80 --height 25   classic BBS dimensions");
    puts("  --help                   show this help");
}

int main(int argc, char **argv) {
    AppConfig config;
    Provider provider;
    char error[256];
    int i;
    memset(&config, 0, sizeof(config));
    memset(&provider, 0, sizeof(provider));
    config.source_kind = "readsb";
    config.range_nm = 100.0;
    config.width = 80;
    config.height = 25;
    config.color = 1;
    for (i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--help") == 0) {
            usage(argv[0]);
            return 0;
        } else if (strcmp(argv[i], "--once") == 0) {
            config.once = 1;
        } else if (strcmp(argv[i], "--source") == 0 && i + 1 < argc) {
            config.source_kind = argv[++i];
        } else if (strcmp(argv[i], "--file") == 0 && i + 1 < argc) {
            config.source_path = argv[++i];
        } else if (strcmp(argv[i], "--receiver-lat") == 0 && i + 1 < argc) {
            config.receiver_latitude = strtod(argv[++i], NULL);
        } else if (strcmp(argv[i], "--receiver-lon") == 0 && i + 1 < argc) {
            config.receiver_longitude = strtod(argv[++i], NULL);
        } else if (strcmp(argv[i], "--range") == 0 && i + 1 < argc) {
            config.range_nm = strtod(argv[++i], NULL);
        } else if (strcmp(argv[i], "--width") == 0 && i + 1 < argc) {
            config.width = atoi(argv[++i]);
        } else if (strcmp(argv[i], "--height") == 0 && i + 1 < argc) {
            config.height = atoi(argv[++i]);
        } else if (strcmp(argv[i], "--color") == 0 && i + 1 < argc) {
            config.color = strcmp(argv[++i], "never") != 0;
        } else {
            fprintf(stderr, "unknown or incomplete option: %s\n", argv[i]);
            return 2;
        }
    }
    if (config.source_path == NULL || config.receiver_latitude < -90.0 ||
        config.receiver_latitude > 90.0 || config.receiver_longitude < -180.0 ||
        config.receiver_longitude > 180.0 || config.range_nm <= 0.0 ||
        config.width != 80 || config.height != 25) {
        fprintf(stderr, "--file, valid receiver coordinates, and 80x25 are required\n");
        return 2;
    }
    if (strcmp(config.source_kind, "readsb") == 0) {
        if (!provider_readsb_file_create(&provider, config.source_path, error, sizeof(error))) {
            fprintf(stderr, "%s\n", error);
            return 3;
        }
    } else if (strcmp(config.source_kind, "dump1090") == 0) {
        if (!provider_dump1090_file_create(&provider, config.source_path, error, sizeof(error))) {
            fprintf(stderr, "%s\n", error);
            return 3;
        }
    } else if (strcmp(config.source_kind, "replay") == 0) {
        if (!provider_replay_csv_create(&provider, config.source_path, error, sizeof(error))) {
            fprintf(stderr, "%s\n", error);
            return 3;
        }
    } else {
        fprintf(stderr, "unsupported provider: %s\n", config.source_kind);
        return 2;
    }
    i = app_run(&config, &provider);
    provider_destroy(&provider);
    return i;
}
