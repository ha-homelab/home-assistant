#!/usr/bin/env python3
"""Restricted SSH command: wake the locally configured LG over Ethernet."""
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import sys
import time

CONFIG = Path(__file__).with_suffix('.json')


def load_target():
    """The operator provisions this private file alongside the relay."""
    config = json.loads(CONFIG.read_text())
    if not isinstance(config, dict) or set(config) != {'mac', 'broadcast'}:
        raise ValueError('Expected mac and broadcast configuration')
    mac = config['mac']
    if not isinstance(mac, str) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', mac):
        raise ValueError('Invalid Ethernet MAC')
    hardware = bytes.fromhex(mac.replace(':', ''))
    if hardware == b'\x00' * 6 or hardware[0] & 1:
        raise ValueError('Expected a unicast Ethernet MAC')
    if not isinstance(config['broadcast'], str):
        raise ValueError('Expected an IPv4 broadcast string')
    address = ipaddress.IPv4Address(config['broadcast'])
    if address.is_loopback or address.is_multicast or address.is_unspecified:
        raise ValueError('Invalid broadcast destination')
    return hardware, str(address)


def main():
    # Reject arbitrary commands rather than interpreting an SSH client's input.
    if os.environ.get("SSH_ORIGINAL_COMMAND") != "wake-living-room-tv":
        print("Only wake-living-room-tv is allowed", file=sys.stderr)
        return 2
    try:
        hardware, broadcast = load_target()
    except (OSError, ValueError):
        print('Provision valid mac and broadcast values in the local relay JSON file', file=sys.stderr)
        return 3
    packet = b"\xff" * 6 + hardware * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(3)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # Let the kernel select the LAN address for this fixed broadcast route.
        for index in range(3):
            if sock.sendto(packet, (broadcast, 9)) != len(packet):
                raise OSError("Incomplete Wake-on-LAN packet")
            if index < 2:
                time.sleep(0.2)
    print(json.dumps({"target": "living_room_tv_77", "packets_sent": 3}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
