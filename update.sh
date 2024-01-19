#!/bin/bash
# Update the system after a random wait
# 3 hours = 10800 seconds
wait_time=$((RANDOM % 10800))
sleep $wait_time

ansible-pull -U https://github.com/kenban/kenban_os/ -C production
