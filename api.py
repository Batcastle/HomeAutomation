#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  api.py
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
import sys
import json
import common
try:
    import ping3
except ImportError:
    print("`ping3' is not available! Likely not running in a venv!", file=sys.stderr)
try:
    import urllib3
except ImportError:
    print("`urllib3' is not available! Likely not running in a venv!",
          file=sys.stderr)


def check_for_presence(presence_check: list, time_out: int) -> bool:
    """Check if any of the provided IP addresses or Hostnames
       are connected to the network.
    """
    for each in presence_check:
        if ping3.ping(each, timeout=time_out):
            return True
    return False


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


def get_sunset_time(loc: dict, tz: str,
                    http: urllib3.poolmanager.PoolManager) -> dict:
    """Get sunset time"""
    url = f"https://api.sunrise-sunset.org/json?lat={loc['lat']}&lng={loc['long']}&tzid={tz}"
    data = json.loads(http.request("GET", url).data.decode())
    return_data = {}
    data = data["results"]
    return_data["sunset"] = common.time_to_unix(data["sunset"], "%I:%M:%S %p")
    return_data["civil_twilight"] = common.time_to_unix(data["civil_twilight_end"],
                                                        "%I:%M:%S %p")
    return_data["nautical_twilight"] = common.time_to_unix(data["nautical_twilight_end"],
                                                           "%I:%M:%S %p")
    return_data["astronomical_twilight"] = common.time_to_unix(data["astronomical_twilight_end"],
                                                               "%I:%M:%S %p")
    return return_data


def get_weather(loc: dict, http: urllib3.poolmanager.PoolManager) -> dict:
    url = "https://api.weather.gov/"
    response = http.request("GET",
                            f"{url}/points/{loc['lat']},{loc['long']}").data.decode()
    response = json.loads(response)
    response = response["properties"]["forecastHourly"]
    response = json.loads(http.request("GET", response).data.decode())
    response = response["properties"]["periods"][0]
    output = {}
    output["temp"] = {
            "temp": response["temperature"],
            "unit": response["temperatureUnit"]
        }
    output["prob_of_precip"] = response["probabilityOfPrecipitation"]["value"] / 100
    output["relative_humid"] = response["relativeHumidity"]["value"] / 100
    output["wind"] = {
            "speed": response["windSpeed"].split(" ")[0],
            "unit": response["windSpeed"].split(" ")[1],
            "direction": response["windDirection"]
        }
    output["other"] = response["shortForecast"]
    return output


def _test(http: urllib3.poolmanager.PoolManager) -> None:
    loc = get_location(http)
    loc = loc["coords"]
    weather = get_weather(loc, http)
    print(f"Weather:\n{json.dumps(weather, indent=2)}")


if __name__ == "__main__":
    import urllib3
    http = urllib3.PoolManager()
    _test(http)
