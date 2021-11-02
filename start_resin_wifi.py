#!/usr/bin/python
import time

import pydbus
import re
import sh
from jinja2 import Template
from netifaces import gateways, interfaces
from os import getenv, path

from lib.utils import generate_perfect_paper_password, get_active_connections


def generate_page(ssid, pswd):
    home = getenv('HOME')
    template_path = path.join(home, 'kenban/templates/hotspot.html')
    with open(template_path) as f:
        template = Template(f.read())

    context = {
        'network': ssid,
        'ssid_pswd': pswd
    }

    with open('/tmp/hotspot.html', 'w') as out_file:
        out_file.write(template.render(context=context))


if __name__ == "__main__":
    bus = pydbus.SystemBus()

    pattern_include = re.compile("wlan*")
    pattern_exclude = re.compile("Kenban-*")

    wireless_connections = get_active_connections(bus)

    if wireless_connections is None:
        exit()

    wireless_connections = [
        c for c in wireless_connections
        if pattern_include.search(str(c['Devices'])) and not pattern_exclude.search(str(c['Id']))
    ]

    if not gateways().get('default') and any(pattern_include.match(i) for i in interfaces()):
        if len(wireless_connections) == 0:
            ssid = 'Kenban-{}'.format(generate_perfect_paper_password(pw_length=4, has_symbols=False))
            ssid_password = generate_perfect_paper_password(pw_length=8, has_symbols=False)
            generate_page(ssid, ssid_password)

            wifi_connect = sh.sudo('wifi-connect', '-s', ssid, '-p', ssid_password, '-o', '9090', _bg=True)
    else:
        exit()

    while not gateways().get('default') and filter(pattern_include.match, interfaces()):
        time.sleep(.5)
