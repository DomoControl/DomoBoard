#!/bin/sh
cd /home/pi/domocontrol
python3 loop.py > /dev/null 2>&1 &
