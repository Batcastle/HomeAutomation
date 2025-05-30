#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  home_automation.py
#
#  Copyright 2025 Thomas Castleman <batcastle@draugeros.org>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#
#
"""Explain what this program does here!!!"""
from __future__ import print_function
import sys
import os
import json
import shutil
import time
import api
import common
import subprocess as subproc
try:
    import urllib3
except ImportError:
    print("`urllib3' is not available! Likely not running in a venv!", file=sys.stderr)
try:
    import phue
except ImportError:
    print("`phue' is not available! Likely not running in a venv!",
          file=sys.stderr)
try:
    import re
except ImportError:
    print("`re' is not available! Likely not running in a venv!",
          file=sys.stderr)

G = "\033[92m"
R = "\033[91m"
NC = "\033[0m"
Y = "\033[93m"
B = '\033[94m'


def eprint(args, *kwargs, color=R):
    """Print to stderr easier"""
    print(color, file=sys.stderr, end="")
    print(args, file=sys.stderr, *kwargs, end="")
    print(NC, file=sys.stderr)


if sys.version_info[0] == 2:
    eprint("Please run with Python 3 as Python 2 is End-of-Life.")
    sys.exit(2)


def is_running_in_venv() -> bool:
    """Check if we are running in a venv"""
    return hasattr(sys,
                   'real_prefix') or (hasattr(sys,
                                              'base_prefix') and sys.base_prefix != sys.prefix)


def need_to_act(on_time_settings: dict, sunset_times: dict, time_format: str) -> bool:
    """This Logic flow determines if anything needs to be done."""
    if on_time_settings == "sunset":
        if time.time() >= sunset_times["sunset"]:
            return True
    else:
        # with the way my settings work, you can use a delta-offset to
        # control when lights turn on
        # this is relative to sunset each day, in hours
        if "-" in on_time_settings:
            # this is for a negative offset
            offset = int(on_time_settings.split("-")[-1]) * 3600
            if time.time() >= (sunset_times["sunset"] - offset):
                return True
        elif "+" in on_time_settings:
            # this is for a positive offset
            offset = int(on_time_settings.split("+")[-1]) * 3600
            if time.time() >= (sunset_times["sunset"] + offset):
                return True
        else:
            offset = common.time_to_unix(on_time_settings, time_format)
            if time.time() >= offset:
                return True
    return False


def is_valid_ip(ip: str) -> bool:
    """Returns True if provided IP is valid. False otherwise. Only works for IPv4."""
    ip_addr = ip.split(".")
    try:
        ip_addr = [int(each) for each in ip_addr]
    except ValueError:
        return False
    if len(ip_addr) != 4:
        return False
    for each in enumerate(ip_addr):
        if 0 > each[1]:
            return False
        if 255 < each[1]:
            return False
    return True


def is_valid_hostname(hostname: str) -> bool:
    """Returns True if provided hostname is valid. False otherwise."""
    # get maximum length
    max_length = int(subproc.check_output(["getconf", "HOST_NAME_MAX"]).decode())
    # Check we are equal to or less than this max length before we do anything.
    if len(hostname) > max_length:
        return False
    regex = re.compile("^[a-z0-9-]*.$", re.IGNORECASE)
    match = regex.match(hostname)
    if match is None:
        return False
    if match.group() == hostname:
        return True
    return False


def main() -> None:
    """Main Setup Loop"""
    # Start out by loading our settings
    settings_file = "home_automation_settings.json"
    with open(settings_file, "r") as file:
        settings = json.load(file)

    # Perform some basic input sanitization and error checking
    for each in settings["brightness"]:
        if 0 <= settings["brightness"][each] <= 1:
            settings["brightness"][each] = round(254 * settings["brightness"][each])
        elif settings["brightness"][each] < 0:
            settings["brightness"][each] = 0
        elif settings["brightness"][each] > 1:
            settings["brightness"][each] = 254
    settings["presence_timeout"] = int(settings["presence_timeout"])
    settings["fork_if_setup"] = bool(settings["fork_if_setup"])
    settings["venv_name"] = str(settings["venv_name"])
    if not is_valid_ip(settings["bridge_ip"]):
        raise ValueError(f"`{settings["bridge_ip"]}' is not a valid IP address!")
    for each in settings["presence_check"]:
        if not is_valid_ip(each):
            if not is_valid_hostname(each):
                raise ValueError(f"`{each}' is not a valid IP address or hostname!")

    # Check if running as root as ping3 requires it.
    if os.geteuid() != 0:
        eprint("Please run this script as root!")
        sys.exit(1)
    # Check if we are running in a venv, if not, set it up, copy ourselves into it, and re-execute
    if not is_running_in_venv():
        eprint(f"{Y}Setting up venv...{NC}")
        subproc.check_call(["python3", "-m", "venv", settings["venv_name"]])
        cmd = f"bash -c 'source ./{settings['venv_name']}/bin/activate && pip3 install {' '.join(settings['deps'])}'"
        subproc.check_call(cmd, shell=True)

        # Copy this file into venv
        main_dest = "./" + settings["venv_name"] + "/" + sys.argv[0].split("/")[-1]
        shutil.copyfile(sys.argv[0], main_dest)

        # Copy common.py into venv
        src = "/".join(sys.argv[0].split("/")[:-1]) + "/common.py"
        dest = "./" + settings["venv_name"] + "/common.py"
        shutil.copyfile(src, dest)

        # Copy api.py into venv
        src = "/".join(sys.argv[0].split("/")[:-1]) + "/api.py"
        dest = "./" + settings["venv_name"] + "/api.py"
        shutil.copyfile(src, dest)

        source = "/".join(sys.argv[0].split("/")[:-1]) + "/" + settings_file
        settings_dest = "./" + settings["venv_name"] + "/" + settings_file
        shutil.copyfile(source, settings_dest)
        eprint(f"{G}Venv ready!{NC}")
        if settings["fork_if_setup"]:
            subproc.Popen([f"./{settings['venv_name']}/bin/python", main_dest])
        else:
            subproc.check_call([f"./{settings['venv_name']}/bin/python", main_dest])
        sys.exit()
    # Create network pool manager
    http = urllib3.PoolManager()
    # Setup complete. Proceding to normal operation.
    home_automation(settings, http)


def home_automation(settings: dict, http) -> None:
    """Main logic loop"""
    # Get location info
    eprint(f"{G}Reached Main Process Loop!{NC}")
    location = api.get_location(http)
    bridge = phue.Bridge(settings["bridge_ip"])
    bridge.connect()
    bridge.get_api()

    sunset_check_time = time.time()
    sunset_times = api.get_sunset_time(location["coords"],
                                       location["tz"], http)
    presence_check_time = time.time()
    presence = api.check_for_presence(settings["presence_check"], settings["presence_timeout"])
    lights_touched = False
    others_touched = False
    midnight = common.time_to_unix("00:00", "%H:%M")
    while True:
        if time.time() >= (sunset_check_time + settings["sunset_time_check_frequency"]):
            sunset_check_time = time.time()
            sunset_times = api.get_sunset_time(location["coords"], location["tz"], http)
        if time.time() >= (presence_check_time + settings["presence_check_frequency"]):
            presence_check_time = time.time()
            presence = api.check_for_presence(settings["presence_check"],
                                              settings["presence_timeout"])

        if not lights_touched:
            if presence:
                if need_to_act(settings["on_time_lights"]["present"],
                               sunset_times, settings["time_format"]):
                    for each in settings["present_lights"]:
                        if not bridge.get_light(each)["state"]["on"]:
                            eprint(f"Turning on: {each}")
                            bridge.set_light(each, "on", True)
                        bridge.set_light(each, "bri", settings["brightness"]["present"])
                    lights_touched = True
            else:
                if need_to_act(settings["on_time_lights"]["not_present"],
                               sunset_times, settings["time_format"]):
                    for each in settings["not_present_lights"]:
                        if not bridge.get_light(each)["state"]["on"]:
                            eprint(f"Turning on: {each}")
                            bridge.set_light(each, "on", True)
                        bridge.set_light(each, "bri",
                                         settings["brightness"]["not_present"])
                    lights_touched = True

        if not others_touched:
            if presence:
                if need_to_act(settings["on_time_other"]["present"],
                               sunset_times, settings["time_format"]):
                    for each in settings["present_other"]:
                        if not bridge.get_light(each)["state"]["on"]:
                            eprint(f"Turning on: {each}")
                            bridge.set_light(each, "on", True)
                    others_touched = True
            else:
                if need_to_act(settings["on_time_other"]["not_present"],
                               sunset_times, settings["time_format"]):
                    for each in settings["not_present_other"]:
                        if not bridge.get_light(each)["state"]["on"]:
                            eprint(f"Turning on: {each}")
                            bridge.set_light(each, "on", True)
                    others_touched = True

        # This is a simple way to tell if we are passed midnight
        if midnight != common.time_to_unix("00:00", "%H:%M"):
            others_touched = False
            lights_touched = False
            midnight = common.time_to_unix("00:00", "%H:%M")
            sunset_check_time = time.time()
            sunset_times = api.get_sunset_time(location["coords"], location["tz"], http)
        time.sleep(settings["main_loop_frequency"])


if __name__ == "__main__":
    main()
