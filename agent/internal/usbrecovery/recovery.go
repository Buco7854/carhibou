// Package usbrecovery provides the narrowly scoped USB reset used to recover a
// wedged SIMCom modem. It deliberately resolves the USB device from a tty and
// refuses every vendor except SIMCom before invoking the reset operation.
package usbrecovery

import (
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

const SIMComVendorID = "1e0e"

var (
	// ErrNotFound means that none of the candidate tty paths currently exists
	// with a corresponding sysfs device.
	ErrNotFound = errors.New("USB recovery tty was not found")
	// ErrUnsupported means that the candidate is not a tty owned by a SIMCom
	// USB device, so no reset was attempted.
	ErrUnsupported = errors.New("USB recovery is unsupported for this tty")
	// ErrPermission means that the tty belongs to a SIMCom USB device, but the
	// process is not allowed to open or reset its usbfs device node.
	ErrPermission = errors.New("permission denied resetting USB device")
	// ErrReset means that the reset operation was attempted and failed.
	ErrReset = errors.New("USB device reset failed")
)

// Device identifies the physical USB device which owns a tty.
type Device struct {
	VendorID     string
	ProductID    string
	BusNumber    int
	DeviceNumber int
	Path         string
}

// ResetOperation resets an already-vetted usbfs device node.
type ResetOperation func(path string) error

// Config supplies alternate roots and a reset operation for tests. Zero values
// select the Linux system locations and USBDEVFS_RESET implementation.
type Config struct {
	SysClassTTYRoot string
	USBBusRoot      string
	Reset           ResetOperation
}

// Recovery resolves and resets eligible tty devices.
type Recovery struct {
	sysClassTTYRoot string
	usbBusRoot      string
	reset           ResetOperation
}

// New constructs a recovery primitive. The returned value is safe to use with
// zero-value Config.
func New(config Config) *Recovery {
	sysClassTTYRoot := config.SysClassTTYRoot
	if sysClassTTYRoot == "" {
		sysClassTTYRoot = "/sys/class/tty"
	}
	usbBusRoot := config.USBBusRoot
	if usbBusRoot == "" {
		usbBusRoot = "/dev/bus/usb"
	}
	reset := config.Reset
	if reset == nil {
		reset = resetUSBDevice
	}
	return &Recovery{
		sysClassTTYRoot: sysClassTTYRoot,
		usbBusRoot:      usbBusRoot,
		reset:           reset,
	}
}

// ResetTTY resolves candidateTTY to its nearest physical USB ancestor and
// resets it only when that ancestor has SIMCom's USB vendor ID. The nearest USB
// ancestor rule is important: traversal never skips a non-SIMCom device to
// reset a hub farther up the tree.
func (recovery *Recovery) ResetTTY(candidateTTY string) (Device, error) {
	device, err := recovery.ResolveTTY(candidateTTY)
	if err != nil {
		return Device{}, err
	}
	return recovery.resetResolved(device)
}

// ResetCandidates examines candidate tty paths in priority order and resets at
// most one physical SIMCom USB device. This is suitable for lists containing
// several interfaces of the same modem: the first eligible tty selects their
// shared parent, and the function returns immediately after one reset.
func (recovery *Recovery) ResetCandidates(candidateTTYs []string) (Device, error) {
	unsupported := false
	for _, candidateTTY := range candidateTTYs {
		device, err := recovery.ResolveTTY(candidateTTY)
		if err == nil {
			return recovery.resetResolved(device)
		}
		if errors.Is(err, ErrNotFound) {
			continue
		}
		if errors.Is(err, ErrUnsupported) {
			unsupported = true
			continue
		}
		return Device{}, err
	}
	if unsupported {
		return Device{}, fmt.Errorf("%w: no candidate tty belongs to a SIMCom USB device", ErrUnsupported)
	}
	return Device{}, fmt.Errorf("%w: no candidate tty has a sysfs device", ErrNotFound)
}

func (recovery *Recovery) resetResolved(device Device) (Device, error) {
	if err := recovery.reset(device.Path); err != nil {
		if errors.Is(err, fs.ErrPermission) {
			return device, fmt.Errorf("%w at %s: %w", ErrPermission, device.Path, err)
		}
		return device, fmt.Errorf("%w at %s: %w", ErrReset, device.Path, err)
	}
	return device, nil
}

// ResolveTTY returns the nearest physical USB device which owns candidateTTY,
// but only if it is a SIMCom device eligible for reset.
func (recovery *Recovery) ResolveTTY(candidateTTY string) (Device, error) {
	ttyName, err := resolveTTYName(candidateTTY)
	if err != nil {
		return Device{}, err
	}
	deviceLink := filepath.Join(recovery.sysClassTTYRoot, ttyName, "device")
	ancestor, err := filepath.EvalSymlinks(deviceLink)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return Device{}, fmt.Errorf("%w: %q has no sysfs device", ErrNotFound, candidateTTY)
		}
		return Device{}, fmt.Errorf("resolve sysfs device for tty %q: %w", candidateTTY, err)
	}

	for {
		attributes, found, err := readUSBAttributes(ancestor)
		if err != nil {
			return Device{}, fmt.Errorf("read USB identity for tty %q at %s: %w", candidateTTY, ancestor, err)
		}
		if found {
			if attributes.vendorID != SIMComVendorID {
				return Device{}, fmt.Errorf(
					"%w: tty %q belongs to USB vendor %s, not SIMCom %s",
					ErrUnsupported,
					candidateTTY,
					attributes.vendorID,
					SIMComVendorID,
				)
			}
			return Device{
				VendorID:     attributes.vendorID,
				ProductID:    attributes.productID,
				BusNumber:    attributes.busNumber,
				DeviceNumber: attributes.deviceNumber,
				Path: filepath.Join(
					recovery.usbBusRoot,
					fmt.Sprintf("%03d", attributes.busNumber),
					fmt.Sprintf("%03d", attributes.deviceNumber),
				),
			}, nil
		}

		parent := filepath.Dir(ancestor)
		if parent == ancestor {
			break
		}
		ancestor = parent
	}
	return Device{}, fmt.Errorf("%w: tty %q has no physical USB ancestor", ErrUnsupported, candidateTTY)
}

type usbAttributes struct {
	vendorID     string
	productID    string
	busNumber    int
	deviceNumber int
}

func readUSBAttributes(directory string) (usbAttributes, bool, error) {
	attributeNames := []string{"idVendor", "idProduct", "busnum", "devnum"}
	values := make(map[string]string, len(attributeNames))
	found := false
	for _, name := range attributeNames {
		content, err := os.ReadFile(filepath.Join(directory, name))
		if err != nil {
			if errors.Is(err, fs.ErrNotExist) {
				continue
			}
			return usbAttributes{}, false, err
		}
		found = true
		values[name] = strings.TrimSpace(string(content))
	}
	if !found {
		return usbAttributes{}, false, nil
	}
	for _, name := range attributeNames {
		if values[name] == "" {
			return usbAttributes{}, false, fmt.Errorf("USB device attribute %s is missing", name)
		}
	}

	vendorID, err := normalizedHexID(values["idVendor"])
	if err != nil {
		return usbAttributes{}, false, fmt.Errorf("invalid idVendor: %w", err)
	}
	productID, err := normalizedHexID(values["idProduct"])
	if err != nil {
		return usbAttributes{}, false, fmt.Errorf("invalid idProduct: %w", err)
	}
	busNumber, err := decimalDeviceNumber("busnum", values["busnum"])
	if err != nil {
		return usbAttributes{}, false, err
	}
	deviceNumber, err := decimalDeviceNumber("devnum", values["devnum"])
	if err != nil {
		return usbAttributes{}, false, err
	}
	return usbAttributes{
		vendorID:     vendorID,
		productID:    productID,
		busNumber:    busNumber,
		deviceNumber: deviceNumber,
	}, true, nil
}

func resolveTTYName(candidate string) (string, error) {
	if strings.TrimSpace(candidate) == "" {
		return "", fmt.Errorf("%w: tty path is empty", ErrUnsupported)
	}
	resolved := candidate
	if strings.ContainsRune(candidate, filepath.Separator) {
		var err error
		resolved, err = filepath.EvalSymlinks(candidate)
		if err != nil {
			if errors.Is(err, fs.ErrNotExist) {
				return "", fmt.Errorf("%w: tty path %q does not exist", ErrNotFound, candidate)
			}
			return "", fmt.Errorf("resolve tty path %q: %w", candidate, err)
		}
	}
	name := filepath.Base(resolved)
	if name == "." || name == string(filepath.Separator) || name == "" {
		return "", fmt.Errorf("%w: invalid tty path %q", ErrUnsupported, candidate)
	}
	return name, nil
}

func normalizedHexID(value string) (string, error) {
	if len(value) != 4 {
		return "", fmt.Errorf("expected four hexadecimal digits, got %q", value)
	}
	if _, err := strconv.ParseUint(value, 16, 16); err != nil {
		return "", fmt.Errorf("expected four hexadecimal digits, got %q", value)
	}
	return strings.ToLower(value), nil
}

func decimalDeviceNumber(name, value string) (int, error) {
	number, err := strconv.Atoi(value)
	if err != nil || number < 1 || number > 999 {
		return 0, fmt.Errorf("invalid %s %q", name, value)
	}
	return number, nil
}
