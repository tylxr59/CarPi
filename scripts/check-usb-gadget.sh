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
else
  echo "UDCs: /sys/class/udc absent"
fi
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
