# Troubleshooting

Run `scripts/doctor.sh` first. It avoids Wi-Fi secrets and Bluetooth keys.

| Symptom | Next check |
| --- | --- |
| Installer refuses OS or architecture | Confirm this is the Pi OS Lite 64-bit target, not the development host or a container. `cat /etc/os-release`, `uname -m`. |
| `bluetoothctl` finds no adapter | Check `rfkill list`, `systemctl status bluetooth`, and onboard radio configuration. |
| SDP channel ambiguous | Inspect `sdptool browse MAC`; pass `--channel N` only after confirming the vehicle's RFCOMM service. |
| RFCOMM connect refused/times out | Pair/trust via `bluetoothctl` and vehicle UI, verify vehicle is discoverable and not already committed to another phone. Do not brute-force channels. |
| Marker or SYN timeout | Capture `btmon` traffic, note peer initiation order, and compare state transitions. This is unverified with Subaru. |
| Bad checksum / out-of-order packet | The parser fails closed; retain a private capture and file a report with metadata. Full retransmission is not implemented. |
| Authentication stops at `auth_unverified` | This is intentional. MFi certificate/signature verification is missing. No Wi-Fi connection is attempted. |
| `h264_v4l2m2m` fails | FFmpeg may list the encoder while the Pi kernel/video device does not support that path. Use `libx264` for the local demo. |
| No image on Subaru | Expected: CarPlay IP sender, pairing and stream transport have not been implemented. |

Do not post raw `.snoop`/`.pcap` captures publicly before checking for identifiers, passwords, certificates and location metadata. No upload is built into this repository.
