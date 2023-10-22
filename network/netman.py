import uuid

import dbus

NM_SERVICE = "org.freedesktop.NetworkManager"
NM_PATH = "/org/freedesktop/NetworkManager"


def get_available_networks():
    bus = dbus.SystemBus()
    nm_settings_proxy = bus.get_object(NM_SERVICE, NM_PATH)
    nm_interface = dbus.Interface(nm_settings_proxy, NM_SERVICE)
    networks = []
    for device_path in nm_interface.GetDevices():
        device_proxy = bus.get_object(NM_SERVICE, device_path)
        device_properties = dbus.Interface(device_proxy, "org.freedesktop.DBus.Properties")

        # Check if the device is a Wi-Fi device
        device_type = device_properties.Get("org.freedesktop.NetworkManager.Device", "DeviceType")
        if device_type == 2:  # NM_DEVICE_TYPE_WIFI = 2
            # Get all access points of the Wi-Fi device
            wireless_iface = dbus.Interface(device_proxy, "org.freedesktop.NetworkManager.Device.Wireless")
            for ap_path in wireless_iface.GetAccessPoints():
                ap_proxy = bus.get_object(NM_SERVICE, ap_path)
                ssid_bytes = bytes(ap_proxy.Get("org.freedesktop.NetworkManager.AccessPoint", "Ssid", dbus_interface=dbus.PROPERTIES_IFACE))
                ssid_str = ssid_bytes.decode('utf-8')
                security = get_wifi_security(ap_proxy)
                print(f"SSID: {ssid_str}, Security: {security}")
                networks.append({"ssid": ssid_str, "security": security})

    return networks


def get_wifi_security(ap):
    # Flags for WPA
    NM_802_11_AP_SEC_NONE = 0x0
    NM_802_11_AP_SEC_PAIR_WEP40 = 0x1
    NM_802_11_AP_SEC_PAIR_WEP104 = 0x2
    NM_802_11_AP_SEC_PAIR_TKIP = 0x4
    NM_802_11_AP_SEC_PAIR_CCMP = 0x8
    NM_802_11_AP_SEC_GROUP_WEP40 = 0x10
    NM_802_11_AP_SEC_GROUP_WEP104 = 0x20
    NM_802_11_AP_SEC_GROUP_TKIP = 0x40
    NM_802_11_AP_SEC_GROUP_CCMP = 0x80
    NM_802_11_AP_SEC_KEY_MGMT_PSK = 0x100
    NM_802_11_AP_SEC_KEY_MGMT_802_1X = 0x200

    wpa_flags = ap.Get("org.freedesktop.NetworkManager.AccessPoint", "WpaFlags", dbus_interface=dbus.PROPERTIES_IFACE)
    rsn_flags = ap.Get("org.freedesktop.NetworkManager.AccessPoint", "RsnFlags", dbus_interface=dbus.PROPERTIES_IFACE)

    if wpa_flags & (NM_802_11_AP_SEC_KEY_MGMT_PSK | NM_802_11_AP_SEC_KEY_MGMT_802_1X):
        return "WPA"
    elif rsn_flags & (NM_802_11_AP_SEC_KEY_MGMT_PSK | NM_802_11_AP_SEC_KEY_MGMT_802_1X):
        if rsn_flags & NM_802_11_AP_SEC_PAIR_CCMP:
            return "WPA2"
        else:
            return "WPA"
    elif wpa_flags & (NM_802_11_AP_SEC_PAIR_WEP40 | NM_802_11_AP_SEC_PAIR_WEP104) or rsn_flags & (NM_802_11_AP_SEC_GROUP_WEP40 | NM_802_11_AP_SEC_GROUP_WEP104):
        return "WEP"
    else:
        return "OPEN"





def save_connection(ssid, password, security):
    wifi_client = {
        'connection': {
            'id': ssid,
            'type': '802-11-wireless',
            'autoconnect': False,
            'uuid': str(uuid.uuid4()),
        },
        '802-11-wireless': {
            'ssid': dbus.ByteArray(ssid.encode('utf-8')),
            'mode': 'infrastructure',  # This means it's a client, not an AP.
        },
        '802-11-wireless-security': {
            'key-mgmt': 'wpa-psk',
            'psk': password
        },
        'ipv4': {
            'method': 'auto',  # This should get IP settings from the DHCP server on the network.
        },
        'ipv6': {
            'method': 'auto'
        }
    }

    return wifi_client


if __name__ == '__main__':
    cons = get_available_networks()
    for c in cons:
        print(c)

