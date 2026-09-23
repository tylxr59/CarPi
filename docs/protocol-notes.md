# Protocol evidence ledger

## Wired USB boundary

**VERIFIED:** Local iAP2 framing and probe consume a byte-stream interface. Bluetooth uses `SocketTransport`; `EndpointTransport` handles partial I/O for a future USB endpoint. No phone-side USB mux/lockdown/carkit implementation is attached. **UPSTREAM-OBSERVED:** one real iPhone exposes a later mux/NCM configuration after `0xC0/0x52`; see [wired research](wired-usb-research.md). **HYPOTHESIS:** the Subaru follows a compatible sequence. **TODO:** capture its requests, implement a phone-side EP0/configuration path, then mux/iAP2 and a shared CarPlay-over-IP session. The W1 NCM link is an independent enumeration test.

Labels refer to evidence for **this repository**, not a claim that upstream behavior works with the Subaru.

## VERIFIED (locally, synthetic tests only)

- `Packet` uses `FF 5A`, a 9-byte header, 16-bit total length, two's-complement header/payload checksums. `PacketStream` handles fragmented/coalesced reads, rejects malformed lengths/checksums and caps input. Synthetic unit tests cover this implementation. No real Subaru bytes have been tested.
- Control messages use `40 40`, 16-bit total length, 16-bit message ID and length-including-header TLVs. The parser bounds checks before decoding. The locally generated Hello World PPM and FFmpeg input path are independent of CarPlay transport.
- The probe sends the `FF 55 02 00 EE 10` detect marker, parses a peer SYN, sends SYN|ACK, checks an ACK, then sends `0x1D00` and parses `0x1D01`. It can send `0x1D02` and ask for `0xAA01`/`0xAA03`, but none of those sequences has been run against the target vehicle.

## UPSTREAM-OBSERVED (behavioral reference)

- [HaToan/carplay-wifi-extractor](https://github.com/HaToan/carplay-wifi-extractor) includes a **client/fake-iPhone** RFCOMM path, iAP2 link negotiation, `StartIdentification` → `IdentificationInformation` → `IdentificationAccepted`, `0xAA00` certificate request, `0xAA02` challenge request and `0x5702` Wi-Fi information request. Its sample client calls auth successful without verifying the accessory signature; this project deliberately does not.
- Its `0x5703` schema maps TLV 1 to SSID and TLV 2 to passphrase. `carpi` only displays SSID and `[REDACTED]` if such a message arrives unsolicited. It does not request Wi-Fi or persist it.
- [lvalen91/carplayd](https://github.com/lvalen91/carplayd) has a Pi **accessory/head-unit** stack and device-verified receiver video. It documents link framing, iAP2 messages, NCM, FunctionFS, pairing/RTSP on the *receiver side* and Pi 4 USB role handling. Receiver success does not verify this phone-source path.
- [doubletake](https://github.com/omarroth/doubletake) implements generic AirPlay **sender** pairing, RTSP, timing, event and video pathways. It targets AirPlay receivers such as Apple TV. Whether Subaru CarPlay accepts the same sender sequence is unknown.

## IP-session research map

| Area | UPSTREAM-OBSERVED reference | Subaru phone-source status |
| --- | --- | --- |
| mDNS / Bonjour | `carplayd`'s receiver advertises `_airplay._tcp`, browses `_carplay-ctrl._tcp`, then requests `/ctrl-int/1/connect` to trigger a phone sender. `doubletake` browses `_airplay._tcp` for generic receivers. | **HYPOTHESIS:** Pi phone may need to advertise `_carplay-ctrl._tcp` and answer a connect request. Capture the Subaru's actual DNS-SD roles first. |
| Pair setup / verify | `doubletake` has sender-side `/pair-setup`, `/pair-verify`, HomeKit-style and legacy variants; `carplayd` receives analogous exchanges. SRP, X25519, signatures, HKDF and encrypted control are involved in observed variants. | **TODO:** identify accepted variant, trust policy, key storage and pairing persistence for Subaru. Do not log derived keys. |
| RTSP / control | `doubletake` uses `/info`, SETUP and RECORD and derives session parameters from receiver responses. `carplayd` accepts receiver-side RTSP. | **TODO:** discover endpoint and CarPlay-specific request bodies/order. Generic AirPlay SETUP cannot be assumed valid. |
| Timing / event | `doubletake` supports timing ports and a separate event connection; its event channel can have independent encryption state. | **TODO:** measure Subaru's negotiated clock, latency, keepalive and event messages. |
| Screen / codec / geometry | Generic sender references choose H.264/HEVC from advertised capabilities and session display information, then send encrypted framed access units. | **TODO:** determine CarPlay display size, pixel orientation, H.264 profile/level, stream key derivation, packetization and presentation timestamps. The local FFmpeg file proves only encoding. |
| Touch / input | `carplayd` implements receiver-side touch/HID handling. | **TODO:** discover corresponding sender-side input channel and mapping. Not required for first static image. |
| Continued iAP2 | `carplayd` carries session control, status and metadata in iAP2 after network establishment in its accessory role. | **HYPOTHESIS:** keep iAP2 alive after the Pi joins Wi-Fi; log subsequent messages before assigning meaning. |

## HYPOTHESIS / TODO

- The Subaru may require Bluetooth pairing/profile registration, a different control session version or a different link opening order. The probe currently uses a deliberately small stop-on-error sequence rather than full retransmission/EAK windows. Test with captures and adapt only to observed behavior.
- MFi validation requires an authorized/distributable trust anchor and correct signature verification. A received certificate and response alone are **not** authentication. Do not send `0xAA05` prematurely.
- Wi-Fi handoff likely precedes CarPlay IP discovery. Determine whether the IVI is an access point, whether the Pi must join it, and which mDNS service appears. Do not assume ordinary `_airplay._tcp` service means CarPlay source authorization.
- CarPlay sender RTSP `SETUP` fields, pair-setup/verify variant, timing, event channel, H.264 encryption/packetization, geometry and touch path must be established from authorized reference/trace work. iAP2 may continue carrying state/status after Wi-Fi handoff. Each unknown needs a test against real hardware; do not infer success from the standalone H.264 sample.
