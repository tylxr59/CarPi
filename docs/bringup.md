# Bring-up from a fresh Pi OS Lite card

1. Flash current **Raspberry Pi OS Lite 64-bit (Trixie)** with Raspberry Pi Imager. Configure SSH and a non-default login in the imager. Boot a Raspberry Pi 4B with its own stable supply, update the OS using `sudo apt update && sudo apt full-upgrade`, then reboot. Keep the vehicle parked for experiments.
2. Clone this repository and inspect [README](../README.md). Run `sudo ./install.sh --dry-run`, then `sudo ./install.sh`. Installation checks Debian-family OS and `aarch64`, warns if the device model is not Pi 4, installs Debian packages and copies the Python standard-library package. The unit is installed **disabled/inactive**. No pairing or networking changes occur.
3. Run `./scripts/doctor.sh` and attach its output when reporting problems. Check that BlueZ lists an adapter, Wi-Fi exists, and `rfkill` does not block Bluetooth. `carpi discover` lists BlueZ-known devices. For active scanning, run `bluetoothctl`, then `scan on`, identify the vehicle, `scan off`, and pair/trust only according to your vehicle's normal UI prompts.
4. Run `sudo carpi probe --target AA:BB:CC:DD:EE:FF -vv`. With a known RFCOMM channel, add `--channel N`; otherwise `sdptool browse` must identify a single iAP service. Keep a terminal open for the probe. It intentionally stops at **auth response unverified**. A failure earlier is valuable evidence; record the state and high-level log, not credentials.
5. Run local video checks: `carpi frame --output hello.ppm`; `carpi video-demo --output hello.h264 --encoder libx264`. Inspect the PPM or decode the H.264 file on another machine if the Pi is headless. Try `--encoder h264_v4l2m2m` only if `doctor.sh` lists it and the Pi kernel exposes an encoder. A listed FFmpeg encoder alone does not prove hardware availability.

Development without install: `PYTHONPATH=src python3 -m carpi --version` and `make test`. The package uses Python 3.11+ standard library. No Docker, desktop, or Apple files are needed.

## Captures

`sudo ./scripts/capture.sh bluetooth [output-dir]` uses `btmon`; `network wlan0` uses `tcpdump`; `usb usbmon1` is reserved for later gadget work. Captures stay local. They can contain BT addresses, credentials and location-related data; sanitize before sharing. In Wireshark, open the `.snoop` or `.pcap` file and filter `bthci_acl`, `btatt`, `tcp`, or `usb` as appropriate. If `usbmon` is absent, load it explicitly with `sudo modprobe usbmon` only for that capture session.

The earliest meaningful vehicle report should include: OS/kernel, BlueZ version, detected RFCOMM channel/service name, final probe state, any parser error, and whether the Subaru requested user confirmation. Do not paste raw authentication payloads.
