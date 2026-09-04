//go:build !linux

package usbrecovery

import "fmt"

func resetUSBDevice(string) error {
	return fmt.Errorf("%w: USBDEVFS_RESET requires Linux", ErrUnsupported)
}
