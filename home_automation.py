#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  home_automation.py
#
#  Copyright 2024 Thomas Castleman <batcastle@draugeros.org>
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
import subprocess as subproc
import urllib3
import ping3
try:
    import phue
except ImportError:
    print("`phue' is not available! Likely not running in a venv!")
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


def check_for_presence(presence_check: list) -> bool:
    """Check if any of the provided IP addresses or Hostnames
       are connected to the network.
    """
    for each in presence_check:
        if ping3.ping(each):
            return True
    return False


def is_running_in_venv() -> bool:
    """Check if we are running in a venv"""
    return hasattr(sys,
                   'real_prefix') or (hasattr(sys,
                                              'base_prefix') and sys.base_prefix != sys.prefix)


def get_location(http) -> dict:
    """Get our general location"""
    data = http.request("GET", "https://ipinfo.io/json").data.decode()
    location = {}
    data = json.loads(data)
    location["city"] = data["city"]
    location["region"] = data["region"]
    location["country"] = data["country"]
    location["coords"] = {
                            "lat": float(data["loc"].split(",")[0]),
                            "long": float(data["loc"].split(",")[1])
                        }
    location["zip"] = data["postal"]
    location["tz"] = data["timezone"]
    return location


def time_to_unix(time_stamp: str, time_format: str) -> float:
    """Convert simple AM/PM time into a Unix time stamp"""
    date = time.strftime("%Y-%m-%d", time.localtime())
    date = time.strptime(f"{ date } { time_stamp }", f"%Y-%m-%d { time_format }")
    return time.mktime(date)


def get_sunset_time(loc: dict, tz: str, http):
    """Get sunset time"""
    url = f"https://api.sunrise-sunset.org/json?lat={ loc['lat'] }&lng={ loc['long'] }&tzid={ tz }"
    data = json.loads(http.request("GET", url).data.decode())
    return_data = {}
    data = data["results"]
    return_data["sunset"] = time_to_unix(data["sunset"], "%I:%M:%S %p")
    return_data["civil_twilight"] = time_to_unix(data["civil_twilight_end"], "%I:%M:%S %p")
    return_data["nautical_twilight"] = time_to_unix(data["nautical_twilight_end"], "%I:%M:%S %p")
    return_data["astronomical_twilight"] = time_to_unix(data["astronomical_twilight_end"], "%I:%M:%S %p")
    return return_data


def main() -> None:
    """Main Setup Loop"""
    # Start out by loading our settings
    settings_file = "home_automation_settings.json"
    with open(settings_file, "r") as file:
        settings = json.load(file)
    # Check if running as root as ping3 requires it.
    if os.geteuid() != 0:
        eprint("Please run this script as root!")
        sys.exit(1)
    # Check if we are running in a venv, if not, set it up, copy ourselves into it, and re-execute
    if not is_running_in_venv():
        print(f"{ Y }Setting up venv...{ NC }")
        subproc.check_call(["python3", "-m", "venv", settings["venv_name"]])
        cmd = f"bash -c 'source ./{ settings['venv_name'] }/bin/activate && pip3 install { ' '.join(settings['deps']) }'"
        subproc.check_call(cmd, shell=True)
        dest = "./" + settings["venv_name"] + "/" + sys.argv[0].split("/")[-1]
        shutil.copyfile(sys.argv[0], dest)
        source = "/".join(sys.argv[0].split("/")[:-1]) + "/" + settings_file
        settings_dest = "./" + settings["venv_name"] + "/" + settings_file
        shutil.copyfile(source, settings_dest)
        print(f"{ G }Venv ready!{ NC }")
        if settings["fork_if_setup"]:
            subproc.Popen([f"./{ settings['venv_name'] }/bin/python", dest])
        else:
            subproc.check_call([f"./{ settings['venv_name'] }/bin/python", dest])
        sys.exit()
    # Create network pool manager
    http = urllib3.PoolManager()
    # Setup complete. Proceding to normal operation.
    home_automation(settings, http)


def home_automation(settings: dict, http) -> None:
    """Main logic loop"""
    # Get location info
    print(f"{ G }Reached Main Process Loop!{ NC }")
    location = get_location(http)
    bridge = phue.Bridge(settings["bridge_ip"])
    bridge.connect()
    bridge.get_api()

    sunset_check_time = time.time()
    sunset_times = get_sunset_time(location["coords"], location["tz"], http)
    presence_check_time = time.time()
    presence = check_for_presence(settings["presence_check"])
    lights_touched = False
    others_touched = False
    midnight = time_to_unix("00:00", "%H:%M")
    while True:
        if time.time() >= (sunset_check_time + settings["sunset_time_check_frequency"]):
            sunset_check_time = time.time()
            sunset_times = get_sunset_time(location["coords"], location["tz"], http)
        if time.time() >= (presence_check_time + settings["presence_check_frequency"]):
            presence_check_time = time.time()
            presence = check_for_presence(settings["presence_check"])

        # Turn the lights on if people are here at the designated time.
        # This section is as much for security as convenience. We turn the lights on both to make potential
        # burglers think we are home, as well as to not have to think about turning the lights on at night.
        if presence:
            if settings["on_time_lights"]["present"] == "sunset":
                if time.time() >= sunset_times["sunset"]:
                    if not lights_touched:
                        print(f"{ B }People are here and it is the configured time! Turning on the lights!{ NC }")
                        for each in settings["present_lights"]:
                            if not bridge.get_light(each)["state"]["on"]:
                                print(f"Turning on: {each}")
                                bridge.set_light(each, "on", True)
                            bridge.set_light(each, "bri", settings["brightness"]["present"])
                        lights_touched = True
            else:
                # with the way my settings work, you can use a delta-offset to
                # control when lights turn on
                # this is relative to sunset each day, in hours
                if "-" in settings["on_time_lights"]["present"]:
                    # this is for a negative offset
                    offset = int(settings["on_time_lights"]["present"].split("-")[-1]) * 3600
                    if time.time() >= (sunset_times["sunset"] - offset):
                        if not lights_touched:
                            print(f"{ B }People are here and it is at/after sunset! Turning on the lights!{ NC }")
                            for each in settings["present_lights"]:
                                if not bridge.get_light(each)["state"]["on"]:
                                    print(f"Turning on: {each}")
                                    bridge.set_light(each, "on", True)
                                bridge.set_light(each, "bri", settings["brightness"]["present"])
                            lights_touched = True
                elif "+" in settings["on_time_lights"]["present"]:
                    # this is for a positive offset
                    offset = int(settings["on_time_lights"]["present"].split("+")[-1]) * 3600
                    if time.time() >= (sunset_times["sunset"] + offset):
                        if not lights_touched:
                            print(f"{ B }People are here and it is at/after sunset! Turning on the lights!{ NC }")
                            for each in settings["present_lights"]:
                                if not bridge.get_light(each)["state"]["on"]:
                                    print(f"Turning on: {each}")
                                    bridge.set_light(each, "on", True)
                                bridge.set_light(each, "bri", settings["brightness"]["present"])
                            lights_touched = True
                else:
                    offset = time_to_unix(settings["on_time_lights"]["present"], settings["time_format"])
                    if time.time() >= offset:
                        if not lights_touched:
                            print(f"{ B }People are here and it is after the configured time! Turning on the lights!{ NC }")
                            for each in settings["present_lights"]:
                                if not bridge.get_light(each)["state"]["on"]:
                                    print(f"Turning on: {each}")
                                    bridge.set_light(each, "on", True)
                                bridge.set_light(each, "bri", settings["brightness"]["present"])
                            lights_touched = True

        # People are not here. Turn the lights on at a slightly different time.
        else:
            if settings["on_time_lights"]["not_present"] == "sunset":
                if time.time() >= sunset_times["sunset"]:
                    if not lights_touched:
                        print(f"{ B }People are NOT here and it is at/after sunset! Turning on the lights!{ NC }")
                        for each in settings["not_present_lights"]:
                            if not bridge.get_light(each)["state"]["on"]:
                                print(f"Turning on: {each}")
                                bridge.set_light(each, "on", True)
                            bridge.set_light(each, "bri", settings["brightness"]["not_present"])
                        lights_touched = True
            else:
                # with the way my settings work, you can use a delta-offset
                # to control when lights turn on
                # this is relative to sunset each day, in hours
                if "-" in settings["on_time_lights"]["not_present"]:
                    # this is for a negative offset
                    offset = int(settings["on_time_lights"]["not_present"].split("-")[-1]) * 3600
                    if time.time() >= (sunset_times["sunset"] - offset):
                        if not lights_touched:
                            print(f"{ B }People are NOT here and it is at/after sunset! Turning on the lights!{ NC }")
                            for each in settings["not_present_lights"]:
                                if not bridge.get_light(each)["state"]["on"]:
                                    print(f"Turning on: {each}")
                                    bridge.set_light(each, "on", True)
                                bridge.set_light(each, "bri", settings["brightness"]["not_present"])
                            lights_touched = True
                elif "+" in settings["on_time_lights"]["not_present"]:
                    # this is for a positive offset
                    offset = int(settings["on_time_lights"]["not_present"].split("+")[-1]) * 3600
                    if time.time() >= (sunset_times["sunset"] + offset):
                        if not lights_touched:
                            print(f"{ B }People are NOT here and it is at/after sunset! Turning on the lights!{ NC }")
                            for each in settings["not_present_lights"]:
                                if not bridge.get_light(each)["state"]["on"]:
                                    print(f"Turning on: {each}")
                                    bridge.set_light(each, "on", True)
                                bridge.set_light(each, "bri", settings["brightness"]["not_present"])
                            lights_touched = True
                else:
                    offset = time_to_unix(settings["on_time_lights"]["not_present"], settings["time_format"])
                    if time.time() >= offset:
                        if not lights_touched:
                            print(f"{ B }People are NOT here and it is after the configured time! Turning on the lights!{ NC }")
                            for each in settings["not_present_lights"]:
                                if not bridge.get_light(each)["state"]["on"]:
                                    print(f"Turning on: {each}")
                                    bridge.set_light(each, "on", True)
                                bridge.set_light(each, "bri", settings["brightness"]["present"])
                            lights_touched = True

        # This section is almost solely for convenience. We want to turn certain things on,
        # at certain times, assuming certain people are home. Otherwise, don't bother
        # turning them on as it would be a waste of power.
        if presence:
            if settings["on_time_other"]["present"] == "sunset":
                if time.time() >= sunset_times["sunset"]:
                    if not others_touched:
                        print(f"{ B }People are here and it is the configured time! Turning on other devices!{ NC }")
                        for each in settings["present_other"]:
                            if not bridge.get_light(each)["state"]["on"]:
                                print(f"Turning on: {each}")
                                bridge.set_light(each, "on", True)
                        others_touched = True
            else:
                # with the way my settings work, you can use a delta-offset to
                # control when lights turn on
                # this is relative to sunset each day, in hours
                if "-" in settings["on_time_other"]["present"]:
                    # this is for a negative offset
                    offset = int(settings["on_time_other"]["present"].split("-")[-1]) * 3600
                    if time.time() >= (sunset_times["sunset"] - offset):
                        if not others_touched:
                            print(f"{ B }People are here and it is at/after sunset! Turning on other devices!{ NC }")
                            for each in settings["present_other"]:
                                if not bridge.get_light(each)["state"]["on"]:
                                    print(f"Turning on: {each}")
                                    bridge.set_light(each, "on", True)
                            others_touched = True
                elif "+" in settings["on_time_other"]["present"]:
                    # this is for a positive offset
                    offset = int(settings["on_time_other"]["present"].split("+")[-1]) * 3600
                    if time.time() >= (sunset_times["sunset"] + offset):
                        if not others_touched:
                            print(f"{ B }People are here and it is at/after sunset! Turning on other devices!{ NC }")
                            for each in settings["present_other"]:
                                if not bridge.get_light(each)["state"]["on"]:
                                    print(f"Turning on: {each}")
                                    bridge.set_light(each, "on", True)
                            others_touched = True
                else:
                    offset = time_to_unix(settings["on_time_other"]["present"], settings["time_format"])
                    if time.time() >= offset:
                        if not others_touched:
                            print(f"{ B }People are here and it is after the configured time! Turning on other devices!{ NC }")
                            for each in settings["present_other"]:
                                if not bridge.get_light(each)["state"]["on"]:
                                    print(f"Turning on: {each}")
                                    bridge.set_light(each, "on", True)
                            others_touched = True

        # People are not here. Turn the lights on at a slightly different time.
        else:
            if settings["on_time_other"]["not_present"] == "sunset":
                if time.time() >= sunset_times["sunset"]:
                    if not others_touched:
                        print(f"{ B }People are NOT here and it is at/after sunset! Turning on other devices!{ NC }")
                        for each in settings["not_present_other"]:
                            if not bridge.get_light(each)["state"]["on"]:
                                print(f"Turning on: {each}")
                                bridge.set_light(each, "on", True)
                        others_touched = True
            else:
                # with the way my settings work, you can use a delta-offset
                # to control when lights turn on
                # this is relative to sunset each day, in hours
                if "-" in settings["on_time_other"]["not_present"]:
                    # this is for a negative offset
                    offset = int(settings["on_time_other"]["not_present"].split("-")[-1]) * 3600
                    if time.time() >= (sunset_times["sunset"] - offset):
                        if not others_touched:
                            print(f"{ B }People are NOT here and it is at/after sunset! Turning on other devices!{ NC }")
                            for each in settings["not_present_other"]:
                                if not bridge.get_light(each)["state"]["on"]:
                                    print(f"Turning on: {each}")
                                    bridge.set_light(each, "on", True)
                            others_touched = True
                elif "+" in settings["on_time_other"]["not_present"]:
                    # this is for a positive offset
                    offset = int(settings["on_time_other"]["not_present"].split("+")[-1]) * 3600
                    if time.time() >= (sunset_times["sunset"] + offset):
                        if not others_touched:
                            print(f"{ B }People are NOT here and it is at/after sunset! Turning on other devices!{ NC }")
                            for each in settings["not_present_other"]:
                                if not bridge.get_light(each)["state"]["on"]:
                                    print(f"Turning on: {each}")
                                    bridge.set_light(each, "on", True)
                            others_touched = True
                else:
                    offset = time_to_unix(settings["on_time_other"]["not_present"], settings["time_format"])
                    if time.time() >= offset:
                        if not others_touched:
                            print(f"{ B }People are NOT here and it is after the configured time! Turning on other devices!{ NC }")
                            for each in settings["not_present_other"]:
                                if not bridge.get_light(each)["state"]["on"]:
                                    print(f"Turning on: {each}")
                                    bridge.set_light(each, "on", True)
                            others_touched = True

        # This is a simple way to tell if we are passed midnight
        if midnight != time_to_unix("00:00", "%H:%M"):
            others_touched = False
            lights_touched = False
            midnight = time_to_unix("00:00", "%H:%M")
        time.sleep(settings["main_loop_frequency"])




if __name__ == "__main__":
    main()
