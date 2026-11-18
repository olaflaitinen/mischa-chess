cmake_minimum_required(VERSION 3.14)

project(mischa VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

option(MISCHA_NATIVE "Optimize for the CPU of the build machine (-march=native)" OFF)
option(MISCHA_POPCNT "Use the hardware POPCNT instruction" OFF)
option(MISCHA_THREADS "Build with Lazy SMP thread support" ON)

file(GLOB MISCHA_SOURCES CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/src/*.cpp)

add_executable(mischa ${MISCHA_SOURCES})

target_compile_definitions(mischa PRIVATE $<$<NOT:$<CONFIG:Debug>>:NDEBUG>)

if(NOT MISCHA_THREADS)
    target_compile_definitions(mischa PRIVATE NO_THREADS)
endif()

if(NOT MISCHA_POPCNT)
    target_compile_definitions(mischa PRIVATE NO_MM_POPCNT)
endif()

find_package(Threads REQUIRED)
target_link_libraries(mischa PRIVATE Threads::Threads)

if(MSVC)
    target_compile_options(mischa PRIVATE /W3 /EHsc)
    target_compile_definitions(mischa PRIVATE _CRT_SECURE_NO_WARNINGS)
else()
    target_compile_options(mischa PRIVATE -Wall -Wno-unknown-pragmas)
    if(MISCHA_NATIVE)
        target_compile_options(mischa PRIVATE -march=native)
    elseif(MISCHA_POPCNT)
        target_compile_options(mischa PRIVATE -mpopcnt)
    endif()
endif()

# the opening books are looked up in a "books" folder next to the executable

add_custom_command(TARGET mischa POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_directory
            ${CMAKE_CURRENT_SOURCE_DIR}/books $<TARGET_FILE_DIR:mischa>/books)

install(TARGETS mischa RUNTIME DESTINATION .)
install(DIRECTORY books DESTINATION .)
install(FILES LICENSE README.md AUTHORS DESTINATION .)

enable_testing()
find_package(Python3 COMPONENTS Interpreter)
if(Python3_FOUND)
    add_test(NAME uci_smoke
             COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/smoke_test.py $<TARGET_FILE:mischa>)
endif()
