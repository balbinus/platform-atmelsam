# Copyright 2014-present Ivan Kravets <me@ikravets.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
    Builder for Atmel SAM series of microcontrollers
"""

from os.path import basename, join

from SCons.Script import (COMMAND_LINE_TARGETS, AlwaysBuild, Builder, Default,
                          DefaultEnvironment)

from platformio.util import get_serialports


def BeforeUpload(target, source, env):  # pylint: disable=W0613,W0621
    board_type = env.subst("$BOARD")
    if "zero" not in board_type:
        env.Append(
            UPLOADERFLAGS=[
                "-U",
                "true" if ("usb" in board_type.lower(
                ) or board_type == "digix") else "false"
            ])

    upload_options = {}
    if "BOARD" in env:
        upload_options = env.BoardConfig().get("upload", {})

    if not upload_options.get("disable_flushing", False):
        env.FlushSerialBuffer("$UPLOAD_PORT")

    before_ports = get_serialports()

    if upload_options.get("use_1200bps_touch", False):
        env.TouchSerialPort("$UPLOAD_PORT", 1200)

    if upload_options.get("wait_for_upload_port", False):
        env.Replace(UPLOAD_PORT=env.WaitForNewSerialPort(before_ports))

    # use only port name for BOSSA
    if "/" in env.subst("$UPLOAD_PORT"):
        env.Replace(UPLOAD_PORT=basename(env.subst("$UPLOAD_PORT")))


env = DefaultEnvironment()

env.Replace(
    AR="arm-none-eabi-ar",
    AS="arm-none-eabi-as",
    CC="arm-none-eabi-gcc",
    CXX="arm-none-eabi-g++",
    OBJCOPY="arm-none-eabi-objcopy",
    RANLIB="arm-none-eabi-ranlib",
    SIZETOOL="arm-none-eabi-size",

    ARFLAGS=["rcs"],

    ASFLAGS=["-x", "assembler-with-cpp"],

    CFLAGS=[
        "-std=gnu11"
    ],

    CCFLAGS=[
        "-g",   # include debugging info (so errors include line numbers)
        "-Os",  # optimize for size
        "-ffunction-sections",  # place each function in its own section
        "-fdata-sections",
        "-Wall",
        "-mthumb",
        "-nostdlib",
        "--param", "max-inline-insns-single=500"
    ],

    CXXFLAGS=[
        "-fno-rtti",
        "-fno-exceptions",
        "-std=gnu++11",
        "-fno-threadsafe-statics"
    ],

    CPPDEFINES=[
        "F_CPU=$BOARD_F_CPU",
        "USBCON"
    ],

    LINKFLAGS=[
        "-Os",
        "-Wl,--gc-sections,--relax",
        "-mthumb",
        "-Wl,--check-sections",
        "-Wl,--unresolved-symbols=report-all",
        "-Wl,--warn-common",
        "-Wl,--warn-section-align"
    ],

    LIBS=["c", "gcc", "m"],

    SIZEPRINTCMD='$SIZETOOL -B -d $SOURCES',

    PROGNAME="firmware",
    PROGSUFFIX=".elf"
)

if "BOARD" in env:
    env.Append(
        CCFLAGS=[
            "-mcpu=%s" % env.BoardConfig().get("build.cpu")
        ],
        LINKFLAGS=[
            "-mcpu=%s" % env.BoardConfig().get("build.cpu")
        ]
    )

env.Append(
    ASFLAGS=env.get("CCFLAGS", [])[:],

    BUILDERS=dict(
        ElfToBin=Builder(
            action=" ".join([
                "$OBJCOPY",
                "-O",
                "binary",
                "$SOURCES",
                "$TARGET"]),
            suffix=".bin"
        ),
        ElfToHex=Builder(
            action=" ".join([
                "$OBJCOPY",
                "-O",
                "ihex",
                "-R",
                ".eeprom",
                "$SOURCES",
                "$TARGET"]),
            suffix=".hex"
        )
    )
)

if env.subst("$BOARD") == "zero":
    env.Replace(
        UPLOADER="openocd",
        UPLOADERFLAGS=[
            "-d2",
            "-s",
            join(env.DevPlatform().get_package_dir("tool-openocd") or "",
                 "share", "openocd", "scripts"),
            "-f",
            join(
                env.DevPlatform().get_package_dir(
                    "framework-arduinosam") or "",
                "variants", env.BoardConfig().get("build.variant"),
                "openocd_scripts",
                "%s.cfg" % env.BoardConfig().get("build.variant")
            ),
            "-c", "\"telnet_port", "disabled;",
            "program", "{{$SOURCES}}",
            "verify", "reset", "0x00002000;", "shutdown\""
        ],
        UPLOADCMD='$UPLOADER $UPLOADERFLAGS'
    )
else:
    env.Replace(
        UPLOADER="bossac",
        UPLOADERFLAGS=[
            "--info",
            "--port", '"$UPLOAD_PORT"',
            "--erase",
            "--write",
            "--verify",
            "--reset",
            "--debug"
        ],
        UPLOADCMD='$UPLOADER $UPLOADERFLAGS $SOURCES'
    )

if "BOARD" in env and "sam3x8e" in env.BoardConfig().get("build.mcu", ""):
    env.Append(
        CPPDEFINES=[
            "printf=iprintf"
        ],

        LINKFLAGS=[
            "-Wl,--entry=Reset_Handler",
            "-Wl,--start-group"
        ],

        UPLOADERFLAGS=[
            "--boot",
        ]

    )
elif "zero" in env.subst("$BOARD"):
    env.Append(
        LINKFLAGS=[
            "--specs=nosys.specs",
            "--specs=nano.specs"
        ]
    )

#
# Target: Build executable and linkable firmware
#

target_elf = env.BuildProgram()

#
# Target: Build the .bin file
#

if "uploadlazy" in COMMAND_LINE_TARGETS:
    target_firm = join("$BUILD_DIR", "firmware.bin")
else:
    target_firm = env.ElfToBin(join("$BUILD_DIR", "firmware"), target_elf)

#
# Target: Print binary size
#

target_size = env.Alias("size", target_elf, "$SIZEPRINTCMD")
AlwaysBuild(target_size)

#
# Target: Upload by default .bin file
#

if env.subst("$BOARD") == "zero":
    upload = env.Alias(["upload", "uploadlazy"], target_firm, "$UPLOADCMD")
else:
    upload = env.Alias(
        ["upload", "uploadlazy"], target_firm,
        [env.AutodetectUploadPort, BeforeUpload, "$UPLOADCMD"])

AlwaysBuild(upload)

#
# Target: Unit Testing
#

AlwaysBuild(env.Alias("test", [target_firm, target_size]))

#
# Setup default targets
#

Default([target_firm, target_size])