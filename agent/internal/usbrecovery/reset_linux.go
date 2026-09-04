//go:build linux

package usbrecovery

import (
	"os"

	"golang.org/x/sys/unix"
)

// USBDEVFS_RESET is _IO('U', 20) from linux/usbdevice_fs.h.
const usbdevfsReset = uint(uintptr('U')<<8 | 20)

func resetUSBDevice(path string) error {
	device, err := os.OpenFile(path, os.O_WRONLY, 0)
	if err != nil {
		return err
	}
	defer device.Close()
	return unix.IoctlSetInt(int(device.Fd()), usbdevfsReset, 0)
}
