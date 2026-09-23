# Architecture and role

The Raspberry Pi must act as the **phone / iPhone / CarPlay source**. The Subaru is the **accessory / head unit / receiver**. Many public projects implement the reverse direction (iPhone → Pi); their working receiver paths cannot be presented as proof of a Pi → Subaru source.

```mermaid
flowchart LR
    P[Pi 4B: fake phone / source] -->|Bluetooth RFCOMM, iAP2| V[Subaru IVI: accessory / receiver]
    P -->|USB-C gadget / NCM development path| V
    V -->|Wi-Fi network information, if offered| P
    P -->|future Wi-Fi IP / AirPlay-CarPlay video| V
    V -->|future input and status| P
```

```mermaid
flowchart TB
    CLI[CLI / explicit probe] --> BT[Bluetooth RFCOMM client]
    BT --> TRANSPORT[iAP2 byte stream boundary]
    USB[USB gadget: ConfigFS NCM W1] --> NCM[NCM kernel interface]
    FFS[Future phone-role mux / EP0 path] -.-> TRANSPORT
    TRANSPORT --> LINK[iAP2 link framing + sequence checks]
    LINK --> CSM[Control message TLV parser]
    CSM --> AUTH[Identification and auth probe]
    CSM -.-> IP[Future CarPlay IP session]
    WIFI[Future Wi-Fi handoff/link] -.-> IP
    NCM -.-> IP
    IP --> MDNS[mDNS discovery]
    IP --> PAIR[Pair setup / pair verify]
    IP --> RTSP[RTSP control, timing, event]
    IP --> VIDEO[H.264 sender]
    VIDEO --> FRAME[Local Hello World renderer]
    IP --> INPUT[Input receiver]
```

The current executable includes the Bluetooth probe, the stream boundary, and an independent USB NCM development gadget. There is no phone-role mux endpoint, wired iAP2 session or CarPlay IP sender. The auth probe stops before asserting `AuthenticationSucceeded` because certificate-chain and challenge-response verification are missing. Wi-Fi credentials are never persisted. The config keys `store_wifi_credentials` and `log_payloads` reserve policy space but do not enable any secret logging or storage in this milestone.

## Checkpoint sequence

1. **Implemented, hardware unverified:** Bluetooth target/service selection, RFCOMM, iAP2 marker and bounded SYN/ACK framing, control-session TLVs, identification request/response/accept, certificate and challenge-response requests. Authentication response is received but *unverified*.
2. **Next:** independently validate the accessory's MFi certificate chain and its signature against a random challenge using distributable trust material and a reviewed implementation. Only then send `AuthenticationSucceeded` and record `auth verified`.
3. **Next:** request `AccessoryWiFiConfigurationInformation` (`0x5702`), parse `0x5703`, redact passphrase, and join the network only through an explicit opt-in command. Observe how the Subaru presents Wi-Fi and whether a CarPlay endpoint becomes discoverable.
4. **Next:** determine actual mDNS role/service (`_airplay._tcp`, `_raop._tcp` or CarPlay-specific advertisement), endpoint ownership and network address from a lawful capture. Establish pair-setup / pair-verify, RTSP setup, timing and event channels. Generic AirPlay mirroring behavior is a reference, not a guarantee of CarPlay compatibility.
5. **Next:** negotiate display geometry and H.264 profile/level, encrypt/packetize and send frames with correct timing. Receive input/status. The exact **missing boundary** is authenticated CarPlay sender-side IP session and SETUP plus encrypted stream formatting; a raw `.h264` file cannot be sent directly to a Subaru display.

## USB milestone

The Pi 4's USB-C controller supports gadget mode under `dwc2` per [Raspberry Pi's OTG guide](https://pip-assets.raspberrypi.com/categories/685-app-notes-guides-whitepapers/documents/RP-009276-WP/Using-OTG-mode-on-Raspberry-Pi-SBCs). `carpi usb setup` now binds a ConfigFS NCM gadget for PC enumeration testing; `teardown` removes it. Host-visible descriptors and kernel support still need Pi validation. [Wired research](wired-usb-research.md) explains why ConfigFS alone cannot implement the observed iPhone configuration reveal or mux. The existing local renderer/encoder remains the video source for a future shared IP sender.
