#!/bin/bash
# -*- coding: utf-8 -*-
#
#  setup.sh
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
set -Ee
set -o pipefail
username=$(whoami)
echo "Configuring your system . . ."
sudo apt install --assume-yes $(<requirements_apt.txt)
sudo cp -v home_automation.service /etc/systemd/system/home_automation.service
sudo sed -i "s:<path to>:$PWD:g" /etc/systemd/system/home_automation.service
sudo sed -i "s:<username>:$username:g" /etc/systemd/system/home_automation.service

echo "Enabling and Starting Home Automation Service . . ."
sudo systemctl enable home_automation.service
sudo systemctl start home_automation.service
git log | grep "^commit " | head -n1 | awk '{print $2}' > .git_commit_number
echo "Configuration and setup complete!"
