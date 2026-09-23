# UART development console (Raspberry Pi 4B)

Use the Pi's GPIO UART as the primary **developer terminal** for bring-up, commands, and live test output. It works without Wi-Fi or Ethernet and remains available while the Pi's USB-C data port is connected to a test host or vehicle. UART is not a CarPlay transport: Bluetooth and USB tests still use their own links to the vehicle. SSH is useful for a second session or file transfer when networking is available.

## Parts and wiring

- A USB-to-**3.3 V TTL UART** adapter with TX, RX, and GND pins, plus three female jumper leads that fit the Pi's 40-pin header. Check the adapter's **signal voltage**, not just its USB supply voltage. Do not use a 5 V TTL adapter or an RS-232 serial cable.
- A computer with a USB port and a serial terminal. The computer powers the adapter only; power the Pi separately with an appropriate supply.
- For vehicle tests, route and secure the lead so it cannot pull on the GPIO header or interfere with driving controls. Perform tests while parked.

With power disconnected, connect by **physical header pin number** (not BCM GPIO number):

| Pi 4B header | Pi signal | USB UART adapter pin |
| --- | --- | --- |
| Pin 6 | GND | GND |
| Pin 8 | GPIO14 / TXD | RXD |
| Pin 10 | GPIO15 / RXD | TXD |

TX and RX cross over. Leave the adapter's **VCC/3V3/5V power pin disconnected**; also leave RTS/CTS disconnected. Never connect the Pi's 5 V pins to the adapter. Check the printed pin labels on both devices before applying power. Raspberry Pi's [UART documentation](https://www.raspberrypi.com/documentation/computers/configuration.html#configure-uarts) identifies GPIO14/15 as the primary UART on pins 8/10 and specifies 3.3 V signalling; its [GPIO documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio-and-the-40-pin-header) identifies pin 6 as ground.

The normal Pi 4B mapping uses the mini UART (`/dev/serial0`, commonly `/dev/ttyS0`) on these pins and the PL011 UART for onboard Bluetooth. Keep that mapping for CarPi's Bluetooth work; do not add `disable-bt` or `miniuart-bt` overlays. Use `/dev/serial0` when checking the Pi, since the underlying device name can change.

## Enable the login console

In Raspberry Pi Imager, set a username and password before the first boot. On a running Raspberry Pi OS Lite card, run `sudo raspi-config`, choose **Interface Options > Serial Port**, and answer **Yes** to the serial login shell prompt. Reboot. Raspberry Pi's [serial port instructions](https://www.raspberrypi.com/documentation/computers/configuration.html#enable-or-disable-serial-port) distinguish the login console from merely enabling UART hardware; CarPi needs the login console.

For a fresh card that must be reachable through UART on its first boot, edit the mounted **boot** partition before inserting it in the Pi:

1. Add `enable_uart=1` to `config.txt` unless it is already enabled. This keeps the Pi 4B's mini UART clock stable.
2. Ensure the single line in `cmdline.txt` contains `console=serial0,115200` exactly once. Preserve the other arguments and keep the file on one line. `console=tty1` may remain for HDMI. If an older serial console argument exists, replace it instead of adding a conflicting one. Remove `quiet` only if you want more kernel messages during boot.

On Raspberry Pi OS Trixie, these files are `/boot/firmware/config.txt` and `/boot/firmware/cmdline.txt` when the Pi is running. The [Raspberry Pi `config.txt` reference](https://www.raspberrypi.com/documentation/computers/config_txt.html#enable_uart) documents both settings. No Bluetooth UART reassignment is needed. After boot, `readlink -f /dev/serial0` and `cat /proc/cmdline` show the UART mapping and console argument. A login prompt after pressing Enter is the practical check.

## Connect from the development computer

With the three signal leads in place, power the Pi from its own supply, then plug the USB UART adapter into the development computer. Find its port (`ls -l /dev/serial/by-id/` on Linux, falling back to `/dev/ttyUSB0` or `/dev/ttyACM0`; `/dev/cu.usb*` on macOS). Open a terminal at **115200 baud, 8 data bits, no parity, 1 stop bit, no hardware or software flow control**. For example, if `picocom` is installed on a Linux computer and the adapter appears as `/dev/ttyUSB0`:

```sh
picocom --baud 115200 --flow n /dev/ttyUSB0
```

Substitute the adapter's actual path, preferably its stable `/dev/serial/by-id/` path when available. If the host reports permission denied, check the port's ownership and grant the host user serial-port access. Press Enter for the Pi login prompt; log in with the account created in Imager. In `picocom`, press Ctrl+A then Ctrl+X to exit. Once connected, reboot the Pi from the terminal to capture kernel and service startup messages. Keep credentials and captured console logs private; the UART connection is local and unencrypted.

Run `./scripts/doctor.sh`, `carpi` diagnostics, probes, and USB status/trace commands from this UART shell. UART provides a login shell, but `git clone`, package updates, and file transfer still need a network connection or removable media. For a long capture and an interactive probe at the same time, use a terminal multiplexer on the Pi if one is available, or use a second SSH session for the capture. UART remains the recovery path if networking or the USB gadget fails. A Pi USB-C gadget test still needs the independent-power arrangement described in the [wired USB workflow](wired-usb.md); the UART cable does not power the Pi.
