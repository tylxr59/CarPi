# Troubleshooting

Run `scripts/doctor.sh` first. It avoids Wi-Fi secrets and Bluetooth keys.

| Symptom | Next check |
| --- | --- |
| Installer refuses OS or architecture | Confirm this is the Pi OS Lite 64-bit target, not the development host or a container. `cat /etc/os-release`, `uname -m`. |
| `bluetoothctl` finds no adapter | Check `rfkill list`, `systemctl status bluetooth`, and onboard radio configuration. |
| `bluetooth doctor` reports ProfileManager1 missing or D-Bus binding error | Install `bluez python3-dbus python3-gi gir1.2-glib-2.0` on Pi OS; run `/usr/bin/python3 -c 'import dbus; from gi.repository import GLib'`. The doctor is read-only and cannot confirm registration permission. |
| Profile registration fails or the adapter stays blocked | Save the exact D-Bus error from `sudo carpi probe ... -vv`, check `rfkill list bluetooth`, and confirm `bluetoothd` is running. The probe restores adapter state it changed. |
| SDP channel ambiguous | Inspect `sdptool browse MAC`; pass `--channel N` only after confirming the vehicle's RFCOMM service. |
| RFCOMM connect refused/times out | Pair/trust via `bluetoothctl` and vehicle UI, verify vehicle is discoverable and not already committed to another phone. Do not brute-force channels. |
| Marker or SYN timeout | Capture `btmon` traffic, note peer initiation order, and compare state transitions. This is unverified with Subaru. |
| Bad checksum / out-of-order packet | The parser fails closed; retain a private capture and file a report with metadata. Full retransmission is not implemented. |
| Authentication stops at `auth_unverified` | This is intentional. MFi certificate/signature verification is missing. For owned-vehicle research only, `--allow-unverified-accessory` requests a Wi-Fi message while clearly reporting authentication as unverified. No Wi-Fi connection is attempted. |
| `h264_v4l2m2m` fails | FFmpeg may list the encoder while the Pi kernel/video device does not support that path. Use `libx264` for the local demo. |
| No image on Subaru | Expected: CarPlay IP sender, pairing and stream transport have not been implemented. |
| `usb doctor` shows no UDC | Check Pi 4 model, `dwc2` overlay and reboot. `install.sh --enable-usb-gadget` can add a backed-up overlay explicitly. |
| `usb setup` says NCM unavailable | Check `CONFIG_USB_CONFIGFS_NCM`/`usb_f_ncm` on the Pi kernel. Other gadgets are left untouched. |
| PC does not enumerate | Verify a data cable, independent Pi power, UDC `state`, and host `lsusb -v -d 1d6b:0104`. A matching VID/PID alone proves nothing about iPhone behavior. |
| Subaru ignores the W1 gadget | W1 has generic NCM descriptors and no Apple mux/configuration reveal. Capture host requests with an external analyzer; Pi usbmon may not show gadget EP0. |
| `usb net-status` shows no IPv6 link-local | Check interface carrier and `ip -6 addr show dev IFACE`. Do not set arbitrary IPv4/DHCP or change Wi-Fi/Ethernet routes. |

Do not post raw `.snoop`/`.pcap` captures publicly before checking for identifiers, passwords, certificates and location metadata. No upload is built into this repository.
