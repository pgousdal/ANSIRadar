cmake_minimum_required(VERSION 3.16)
project(ansiradar80 VERSION 0.1.0 LANGUAGES C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

add_library(ansiradar80_core
    csrc/models/aircraft.c
    csrc/providers/providers.c
    csrc/renderer/ansi.c
    csrc/renderer/radar.c
    csrc/renderer/screen.c
    csrc/ui/input.c
)
target_include_directories(ansiradar80_core PUBLIC include)
target_compile_options(ansiradar80_core PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(ansiradar80_core PUBLIC m)

add_executable(ansiradar80
    csrc/core/main.c
    csrc/ui/radar_view.c
)
target_include_directories(ansiradar80 PRIVATE include)
target_link_libraries(ansiradar80 PRIVATE ansiradar80_core m)

enable_testing()
add_executable(ansiradar80_test ctests/test_core.c)
target_include_directories(ansiradar80_test PRIVATE include)
target_link_libraries(ansiradar80_test PRIVATE ansiradar80_core m)
add_test(NAME ansiradar80_core COMMAND ansiradar80_test
    ${CMAKE_CURRENT_SOURCE_DIR}/fixtures80/readsb.json)

install(TARGETS ansiradar80 RUNTIME DESTINATION bin)
install(DIRECTORY include/ DESTINATION include)
