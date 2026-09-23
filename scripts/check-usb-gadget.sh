#!/usr/bin/env bash
set -euo pipefail
echo "== USB gadget prerequisites (read-only) =="
if [[ -d /sys/bus/platform/drivers/dwc2 ]]; then
  echo "dwc2 platform driver: present"
else
  echo "dwc2 platform driver: not visible"
fi
if [[ -d /sys/class/udc ]]; then
  echo "UDCs: $(find /sys/class/udc -mindepth 1 -maxdepth 1 -printf '%f ' 2>/dev/null)"
  for udc in /sys/class/udc/*; do
    [[ -d $udc ]] || continue
    echo "UDC $(basename "$udc") state: $(cat "$udc/state" 2>/dev/null || echo unknown)"
    echo "UDC $(basename "$udc") driver: $(basename "$(readlink -f "$udc/device/driver" 2>/dev/null || echo unknown)")"
  done
else
  echo "UDCs: /sys/class/udc absent"
fi
if [[ -d /sys/class/usb_role ]]; then
  for role in /sys/class/usb_role/*/role; do
    [[ -r $role ]] && echo "USB role: $(cat "$role")"
  done
fi
if [[ -d /sys/kernel/config/usb_gadget/carpi ]]; then
  echo "carpi gadget UDC: $(cat /sys/kernel/config/usb_gadget/carpi/UDC 2>/dev/null || true)"
  for function in /sys/kernel/config/usb_gadget/carpi/functions/*; do
    [[ -d $function ]] && echo "Gadget function: $(basename "$function")"
  done
fi
if [[ -d /sys/kernel/debug/usb/usbmon ]]; then echo "usbmon: available"; else echo "usbmon: unavailable/not mounted"; fi
for name in USB_F_FS USB_CONFIGFS_NCM USB_MON; do
  CONFIG_FILE="/boot/config-$(uname -r)"
  if [[ -r $CONFIG_FILE ]]; then
    grep -E "^CONFIG_${name}=" "$CONFIG_FILE" || true
  else
    echo "CONFIG_${name}: kernel config unavailable"
  fi
done
if command -v modinfo >/dev/null; then
  for module in libcomposite usb_f_fs usb_f_ncm usbmon; do
    if modinfo "$module" >/dev/null 2>&1; then
      echo "Available module: $module"
    fi
  done
fi
if [[ -d /sys/kernel/config/usb_gadget/carpi/functions ]]; then
  echo "USB network candidates (no addresses/serials):"
  for function in /sys/kernel/config/usb_gadget/carpi/functions/ncm.*; do
    [[ -r $function/ifname ]] || continue
    iface=$(cat "$function/ifname")
    if [[ -n $iface && -r /sys/class/net/$iface/carrier ]]; then
      echo "NCM interface $iface carrier: $(cat "/sys/class/net/$iface/carrier" 2>/dev/null || echo unknown)"
    fi
  done
fi
echo "Separate Pi power cannot be verified in software."
if [[ -d /sys/kernel/config/usb_gadget ]]; then
  echo "ConfigFS usb_gadget: available"
elif [[ -d /sys/kernel/config ]]; then
  echo "ConfigFS: present; usb_gadget not mounted/available"
else
  echo "ConfigFS: absent"
fi
if [[ -r /proc/modules ]]; then
  awk '$1 ~ /^(dwc2|libcomposite|usb_f_ncm|usb_f_fs|usbmon)$/ {print "Module: " $1}' /proc/modules
fi
if [[ -r /boot/firmware/config.txt ]]; then
  sed -n '/^[[:space:]]*dtoverlay=dwc2/p' /boot/firmware/config.txt
fi
