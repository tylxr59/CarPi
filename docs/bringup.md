# Bring-up from a fresh Pi OS Lite card

1. Flash current **Raspberry Pi OS Lite 64-bit (Trixie)** with Raspberry Pi Imager. Configure SSH and a non-default login in the imager. Boot a Raspberry Pi 4B with its own stable supply, update the OS using `sudo apt update && sudo apt full-upgrade`, then reboot. Keep the vehicle parked for experiments.
2. Clone this repository and inspect [README](../README.md). Run `sudo ./install.sh --dry-run`, then `sudo ./install.sh`. Installation checks Debian-family OS and `aarch64`, warns if the device model is not Pi 4, and installs `bluez`, `python3-dbus`, `python3-gi`, and `gir1.2-glib-2.0` alongside the existing tools. The unit is installed **disabled/inactive**. No pairing or networking changes occur.
3. Run `./scripts/doctor.sh` and attach its output when reporting problems. Check that BlueZ lists an adapter, Wi-Fi exists, and `rfkill` does not block Bluetooth. `carpi discover` lists BlueZ-known devices. For active scanning, run `bluetoothctl`, then `scan on`, identify the vehicle, `scan off`, and pair/trust only according to your vehicle's normal UI prompts.
4. Run `sudo carpi bluetooth doctor`, then `sudo carpi probe --target AA:BB:CC:DD:EE:FF -vv`. With a known RFCOMM channel, add `--channel N`; otherwise `sdptool browse` must identify a single iAP service. The normal probe stops at **auth response unverified**. If it reaches that point, run `sudo carpi probe --target AA:BB:CC:DD:EE:FF --allow-unverified-accessory -vv` for research observation of Wi-Fi configuration. This does not cryptographically verify authentication, connect to Wi-Fi, or start CarPlay over IP. Save both final summaries.
5. Run local video checks: `carpi frame --output hello.ppm`; `carpi video-demo --output hello.h264 --encoder libx264`. Inspect the PPM or decode the H.264 file on another machine if the Pi is headless. Try `--encoder h264_v4l2m2m` only if `doctor.sh` lists it and the Pi kernel exposes an encoder. A listed FFmpeg encoder alone does not prove hardware availability.

Development without install: `PYTHONPATH=src python3 -m carpi --version` and `make test`. Hardware-free tests use Python 3.11+ standard library; a live BlueZ probe needs the Debian D-Bus/GLib packages above. No Docker, desktop, or Apple files are needed.

## Wired development path

Follow [wired USB workflow](wired-usb.md) after installation: `sudo carpi usb doctor`, `sudo carpi usb setup`, `sudo carpi usb trace`, then `sudo carpi usb teardown`. Start with a Linux/macOS test computer. The development NCM gadget has not been verified on Pi hardware and does not implement the iPhone mux or CarPlay session.

## Captures

`sudo carpi capture bluetooth --output-dir captures` uses `btmon` until Ctrl+C. The existing `sudo ./scripts/capture.sh bluetooth [output-dir]` also works. `network wlan0` uses `tcpdump`. `sudo carpi capture network` selects the active NCM interface. `sudo carpi capture usb` uses `usbmon0`, but Pi-side usbmon may not expose gadget requests; see [wired workflow](wired-usb.md) for host-side capture. Captures stay local and can contain identifiers, pairing information, protocol payloads and credentials; sanitize before sharing. See [First vehicle test](../README.md#first-vehicle-test).

The earliest meaningful vehicle report should include: OS/kernel, BlueZ version, detected RFCOMM channel/service name, final probe state, any parser error, and whether the Subaru requested user confirmation. Do not paste raw authentication payloads.
