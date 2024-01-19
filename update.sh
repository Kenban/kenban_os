#!/bin/bash

update() {
  echo "Updating NoticeHome"
  ansible-pull -U https://github.com/kenban/kenban_os/ -C production
}
# Update the system after a random wait
if [[ "$1" == "--no-wait" ]]; then
    update
    exit 0
fi
# 3 hours = 10800 seconds
wait_time=$((RANDOM % 10800))
echo "Waiting $wait_time seconds for update"
sleep $wait_time
update

