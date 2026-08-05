# Architecture

M1 has four layers: the readsb source performs one explicit read and parses an
immutable snapshot; domain models preserve normalized aircraft facts; radar
helpers derive distance and bearing; renderers emit stable text or JSON. The CLI
connects these layers and maps expected failures to documented exit codes.

Interactive input, full-screen ANSI radar, trails, replay, persistence, SDR
control, enrichment, route lookup, network polling, and telemetry are outside M1.
