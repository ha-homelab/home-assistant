# Tapo camera DHCP reservations

Camera MAC addresses, local DNS names, device-to-room mappings, and registry
identities are maintained in the private router configuration and Home Assistant
registries. This repository keeps the operating procedure, not a copy of that
inventory. The seven reservations were verified on September 26, 2026 (PDT).

## Network and ownership

OpenWrt on **h3** owns the DHCP reservations and local DNS. Camera DHCP remains
enabled. Stable addresses come from reservations matched to each camera's MAC
address, rather than manual IP settings on the cameras. Obtain the actual MAC,
reserved address, and DNS name from h3 before maintenance. Nothing in this
repository replaces or changes the working h3 configuration.

## Identification and migration procedure

Read-only discovery on September 26, 2026 matched DHCP lease MAC addresses against
each camera's ONVIF network interface. All seven cameras accepted the existing
Front local Camera Account on port `2020`; all reported DHCP enabled and a `/20`
prefix. Device-information calls confirmed one C120, two C225 and four C201 cameras.
Credentials remain private and are not included in this documentation.

Before changing h3, save its current `/etc/config/dhcp` to a protected operational
backup outside the repository. Retain the corresponding router configuration
backup and its timestamp. Check the proposed addresses and DNS names against
existing reservations, leases, and reachable devices before allocating them.

The pre-change DHCP configuration was backed up on h3 at
`/root/config-backups/dhcp.before-tapo-20260927T002426Z`. The DHCP service reloaded,
its configuration passed syntax validation, and unrelated UCI configuration was
unchanged. Each C201 acknowledged one ONVIF reboot and returned at its reserved
address in approximately 41 seconds. All four retained their expected MAC, model,
serial number, DHCP setting, and `/20` prefix. Their new leases, short and fully
qualified DNS names, and absence of the old leases were verified.

A final read-only check at `2026-09-27T00:29:02Z` confirmed ONVIF authentication,
identity, reservations, leases, and DNS for all seven cameras. The three existing
cameras kept their addresses and were not rebooted. The post-change DHCP snapshot
is `/root/config-backups/dhcp.after-tapo-20260927T002902Z` on h3. These protected
files contain DHCP configuration only, not a full router backup.

Apply the four named MAC reservations through OpenWrt UCI, commit the DHCP
configuration, and reload the DHCP service. Avoid a router reboot or network
restart. Then process the four C201 cameras **one at a time**:

1. Confirm the expected MAC, ONVIF model, and serial number at the current address.
2. Request the camera's supported ONVIF `SystemReboot` to renew DHCP after restart.
3. Wait for the reserved address to answer and confirm its DHCP lease, MAC,
   ONVIF model, and serial identity. Check that camera DHCP remains enabled.
4. Resolve the camera's short name and fully qualified local DNS name through h3.
   Confirm the previous dynamic address is no longer assigned to that MAC before
   proceeding to the next camera.

Do not regard an open port or a successful ping as sufficient identity validation.
If a camera does not return, stop the sequence and inspect its current lease and
neighbor entry before repeating any action.

## Home Assistant scope

The DHCP operation established stable addresses without adding video streams or
HA camera integrations. The subsequent [fleet ONVIF onboarding](tapo-onvif-events.md)
has configured all seven cameras for event-only HA use; its verification and
operating limits are documented separately.

The [Front ONVIF event pilot](tapo-onvif-events-pilot.md) documents the existing
event-only HA setup and the subsequent onboarding checks. Front keeps its current
address and existing Frigate, Kerberos, and go2rtc consumers. Its existing video
traffic is not reduced by this reservation work.

## Restore and rollback

For a fresh router restore, restore the base OpenWrt configuration from its
separate full backup, then reconcile its DHCP host sections with the private
camera inventory and the post-change DHCP snapshot. The pre-change snapshot
does not contain the four new reservations. Revalidate one camera at a time
using its MAC and ONVIF identity. Camera accounts and HA integration credentials
must be restored from their private backups, not from this repository.

To undo this change, remove only the four added C201 reservation sections identified
in the private router inventory, or restore the saved DHCP configuration after reviewing any
newer unrelated changes. Commit and reload DHCP, then restart affected cameras
sequentially and discover their new leases by MAC. Removing a reservation does
not guarantee a camera will reclaim its former dynamic address. Keep the three
pre-existing Tapo reservations and the rest of the router configuration intact.
