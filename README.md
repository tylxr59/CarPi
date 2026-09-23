# carpi

`carpi` is a research project to make a Raspberry Pi 4B act as the **phone / iPhone / CarPlay source** for a real vehicle. The Pi is **not** a CarPlay receiver or head unit. The target is a developer-controlled 2024 Subaru Crosstrek Limited. Subaru [lists wireless CarPlay for this trim](https://www.subaru.com/content/dam/subaru/downloads/pdf/brochures/2024/2024_Crosstrek_Brochure_072823.pdf); this repository has **no Pi or vehicle test result yet**.

The eventual “Hello World” means a Pi-generated frame with `Hello World`, `carpi`, resolution, counter and time appearing on the Subaru display. Today, the frame and H.264 sample are **local artifacts only**. No CarPlay IP sender or screen transport is implemented.

| Component | Status |
| --- | --- |
| Pi 4 environment detection | Implemented; validate with `scripts/doctor.sh` on Pi |
| Bluetooth device listing / SDP | Implemented; needs Pi + vehicle test |
| RFCOMM client transport | Implemented; needs Pi + vehicle test |
| iAP2 framing, checksums, SYN/ACK | Unit tested; vehicle negotiation unverified |
| Identification | Probe sends/receives messages; vehicle acceptance unverified |
| Authentication | Requests cert/challenge response, **does not verify**; stops there |
| Wi-Fi handoff | 0x5703 parser/redaction only; not requested or connected |
| CarPlay IP discovery | Research/design only |
| AirPlay pairing and RTSP | Missing |
| H.264 test-frame generation | Local PPM and H.264 demo implemented; FFmpeg integration needs Pi test |
| Video on vehicle display | Missing |
| Touch input, audio | Not targeted yet |
| Wired USB transport | Future; no gadget setup command yet |

## Quick start

On Raspberry Pi OS Lite 64-bit Trixie, separately power the Pi, enable SSH, then:

```sh
git clone <your-repository-url> carpi
cd carpi
sudo ./install.sh --dry-run
sudo ./install.sh
./scripts/doctor.sh
carpi discover
sudo carpi probe --target AA:BB:CC:DD:EE:FF -vv
```

Pair/trust the vehicle through `bluetoothctl` first if required. `--channel N` overrides SDP selection. The probe contacts the specified vehicle only when invoked. It stops after receiving an unverified authentication response. `-vv` logs packet **metadata**, not credential payloads. Installed configuration at `/etc/carpi/carpi.toml` loads automatically if present; `--config PATH` selects another file. Repository runs use `PYTHONPATH=src python3 -m carpi ...`.

```sh
PYTHONPATH=src python3 -m carpi frame --output hello.ppm
PYTHONPATH=src python3 -m carpi video-demo --output hello.h264
make test
sudo ./uninstall.sh --dry-run
```

`video-demo` defaults to software `libx264`; `--encoder h264_v4l2m2m` attempts a Pi hardware path. Neither sends bytes to the vehicle. The installer neither starts nor enables its idle systemd unit.

See [bring-up](docs/bringup.md), [architecture](docs/architecture.md), [protocol notes](docs/protocol-notes.md), [upstream research](docs/upstream-research.md), and [troubleshooting](docs/troubleshooting.md).

This work touches only infotainment projection. It has no CAN, ECU, diagnostic, vehicle control or safety-system functionality. Captures may expose identifiers and credentials; keep them private. No Apple binaries, private documents, certificates or keys are included.
