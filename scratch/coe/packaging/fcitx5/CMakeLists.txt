cmake_minimum_required(VERSION 3.16)
project(coe-fcitx5 VERSION 0.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(Fcitx5Core REQUIRED)
find_package(Fcitx5Utils REQUIRED)
find_package(PkgConfig REQUIRED)
pkg_check_modules(DBUS REQUIRED IMPORTED_TARGET dbus-1)

execute_process(
    COMMAND pkg-config --variable=prefix Fcitx5Core
    OUTPUT_VARIABLE FCITX5_CORE_PREFIX
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
execute_process(
    COMMAND pkg-config --variable=libdir Fcitx5Core
    OUTPUT_VARIABLE FCITX5_CORE_LIBDIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
execute_process(
    COMMAND pkg-config --variable=datadir Fcitx5Core
    OUTPUT_VARIABLE FCITX5_CORE_DATADIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
)

if(NOT FCITX5_CORE_PREFIX OR NOT FCITX5_CORE_LIBDIR)
    message(FATAL_ERROR "Failed to query Fcitx5 install layout via pkg-config")
endif()

if(NOT FCITX5_CORE_DATADIR)
    set(FCITX5_CORE_DATADIR "${FCITX5_CORE_PREFIX}/share")
endif()

file(RELATIVE_PATH COE_FCITX_INSTALL_LIBDIR "${FCITX5_CORE_PREFIX}" "${FCITX5_CORE_LIBDIR}")
file(RELATIVE_PATH COE_FCITX_INSTALL_DATADIR "${FCITX5_CORE_PREFIX}" "${FCITX5_CORE_DATADIR}")

add_library(coefcitx MODULE
    src/coe_module.cpp
)

target_link_libraries(coefcitx
    PRIVATE
        Fcitx5::Core
        Fcitx5::Utils
        PkgConfig::DBUS
)

target_include_directories(coefcitx
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/src
)

set_target_properties(coefcitx PROPERTIES
    PREFIX "lib"
    OUTPUT_NAME "coefcitx"
)

install(TARGETS coefcitx
    LIBRARY DESTINATION ${COE_FCITX_INSTALL_LIBDIR}/fcitx5
)

install(FILES addon/coe.conf
    DESTINATION ${COE_FCITX_INSTALL_DATADIR}/fcitx5/addon
)
