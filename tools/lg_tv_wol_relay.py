#!/usr/bin/env python3
"""Restricted SSH command on syn: wake only the living-room LG over Ethernet."""
import json
import os
import socket
import sys
import time


def main():
    # Reject arbitrary commands rather than interpreting an SSH client's input.
    if os.environ.get("SSH_ORIGINAL_COMMAND") != "wake-living-room-tv":
        print("Only wake-living-room-tv is allowed", file=sys.stderr)
        return 2
    packet = b"\xff" * 6 + bytes.fromhex("d0cdbf6670b2") * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(3)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # Let the kernel select the LAN address for this fixed broadcast route.
        for index in range(3):
            if sock.sendto(packet, ("192.168.175.255", 9)) != len(packet):
                raise OSError("Incomplete Wake-on-LAN packet")
            if index < 2:
                time.sleep(0.2)
    print(json.dumps({"target": "living_room_tv_77", "packets_sent": 3}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
