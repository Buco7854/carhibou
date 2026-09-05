// Package usbrecovery provides narrowly scoped USB reset primitives. The scope
// is the devices the agent was configured to use: a caller resolves its own
// ttys to physical USB devices and allows exactly those. Nothing here knows a
// vendor by name, because the agent has to work with whatever modem and adapter
// it was pointed at.
package usbrecovery

import (
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// usbHubDeviceClass is bDeviceClass 09. A hub owns every tty below it, so
// resetting one takes down devices nobody asked about — including, on a Pi Zero,
// the root hub the agent's own modem hangs from.
const usbHubDeviceClass = "09"

// Cooldown prevents repeated physical resets from turning one hardware fault
// into a reset loop.
const Cooldown = 15 * time.Minute

var (
	// ErrNotFound means that none of the candidate tty paths currently exists
	// with a corresponding sysfs device.
	ErrNotFound = errors.New("USB recovery tty was not found")
	// ErrUnsupported means that the candidate is not owned by one of the USB
	// devices the caller explicitly allowed, so no reset was attempted.
	ErrUnsupported = errors.New("USB recovery is unsupported for this tty")
	// ErrPermission means that the tty belongs to an allowed USB device, but the
	// process is not allowed to open or reset its usbfs device node.
	ErrPermission = errors.New("permission denied resetting USB device")
	// ErrReset means that the reset operation was attempted and failed.
	ErrReset = errors.New("USB device reset failed")
	// ErrCoolingDown means that no reset was attempted because the previous one
	// was too recent. A caller diagnosing a failure has to tell that apart from a
	// reset that ran and did not help: one says the hardware is beyond this
	// remedy, the other says the remedy has not been tried yet.
	ErrCoolingDown = errors.New("USB reset skipped during the cooldown after the previous one")
)

// DeviceID names a physical USB device by what udev can match on: its vendor and
// product, plus its serial when the device publishes one. An empty Serial means
// "any unit of this product", which is what a device without a serial leaves.
type DeviceID struct {
	VendorID  string
	ProductID string
	Serial    string
}

func (id DeviceID) String() string {
	if id.Serial == "" {
		return id.VendorID + ":" + id.ProductID
	}
	return id.VendorID + ":" + id.ProductID + " serial " + id.Serial
}

// Device identifies the physical USB device which owns a tty.
type Device struct {
	VendorID     string
	ProductID    string
	Serial       string
	Manufacturer string
	Product      string
	BusNumber    int
	DeviceNumber int
	Path         string
}

func (device Device) ID() DeviceID {
	return DeviceID{VendorID: device.VendorID, ProductID: device.ProductID, Serial: device.Serial}
}

// String names the device the way its descriptors do, so a diagnostic that found
// nothing the agent was configured with can say what it did find.
func (device Device) String() string {
	description := device.VendorID + ":" + device.ProductID
	for _, descriptor := range []string{device.Manufacturer, device.Product} {
		if descriptor != "" {
			description += " " + strconv.Quote(descriptor)
		}
	}
	if device.Serial != "" {
		description += " serial " + device.Serial
	}
	return description
}

// ResetOperation resets an already-vetted usbfs device node.
type ResetOperation func(path string) error

// Config supplies alternate roots and a reset operation for tests. Zero values
// select the Linux system locations and USBDEVFS_RESET implementation.
type Config struct {
	SysClassTTYRoot string
	USBBusRoot      string
	Reset           ResetOperation
	// AllowedDevices is the set a reset may touch. Leaving it empty allows
	// nothing, so a caller that has not said which devices are its own cannot
	// reset anything by accident.
	AllowedDevices []DeviceID
}

// Recovery resolves and resets eligible tty devices.
type Recovery struct {
	sysClassTTYRoot string
	usbBusRoot      string
	reset           ResetOperation
	allowed         []DeviceID
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
	allowed := make([]DeviceID, 0, len(config.AllowedDevices))
	for _, device := range config.AllowedDevices {
		allowed = append(allowed, DeviceID{
			VendorID:  strings.ToLower(device.VendorID),
			ProductID: strings.ToLower(device.ProductID),
			Serial:    device.Serial,
		})
	}
	return &Recovery{
		sysClassTTYRoot: sysClassTTYRoot,
		usbBusRoot:      usbBusRoot,
		reset:           reset,
		allowed:         allowed,
	}
}

// ResetTTY resolves candidateTTY to its nearest physical USB ancestor and resets
// it only when that ancestor is one of the allowed devices. The nearest USB
// ancestor rule is important: traversal never skips an unrelated device to reset
// a hub farther up the tree, and a hub is refused outright.
func (recovery *Recovery) ResetTTY(candidateTTY string) (Device, error) {
	device, err := recovery.ResolveTTY(candidateTTY)
	if err != nil {
		return Device{}, err
	}
	return recovery.resetResolved(device)
}

// ResetCandidates examines candidate tty paths in priority order and resets at
// most one allowed physical USB device. This is suitable for lists containing
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
		return Device{}, fmt.Errorf("%w: no candidate tty belongs to a configured USB device", ErrUnsupported)
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
// but only when that device is one this recovery path was allowed.
func (recovery *Recovery) ResolveTTY(candidateTTY string) (Device, error) {
	device, err := recovery.Identify(candidateTTY)
	if err != nil {
		return Device{}, err
	}
	if !recovery.allows(device) {
		return Device{}, fmt.Errorf(
			"%w: tty %q belongs to USB device %s, which is not one this agent was configured with",
			ErrUnsupported, candidateTTY, device,
		)
	}
	return device, nil
}

func (recovery *Recovery) allows(device Device) bool {
	for _, allowed := range recovery.allowed {
		if allowed.VendorID != device.VendorID || allowed.ProductID != device.ProductID {
			continue
		}
		// A device that publishes no serial cannot be told from another unit of
		// the same product, and pinning a serial that does not exist would refuse
		// the only device there is.
		if allowed.Serial == "" || allowed.Serial == device.Serial {
			return true
		}
	}
	return false
}

// Identify returns the nearest physical USB ancestor of candidateTTY without
// consulting the allowed set. Resolving a configured tty is how that set is
// built in the first place, so it cannot be gated by it; a hub is still refused,
// because nothing about this path should ever reset one.
func (recovery *Recovery) Identify(candidateTTY string) (Device, error) {
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
			if attributes.deviceClass == usbHubDeviceClass {
				return Device{}, fmt.Errorf(
					"%w: tty %q hangs from USB hub %s:%s, which is never reset",
					ErrUnsupported, candidateTTY, attributes.vendorID, attributes.productID,
				)
			}
			return Device{
				VendorID:     attributes.vendorID,
				ProductID:    attributes.productID,
				Serial:       attributes.serial,
				Manufacturer: attributes.manufacturer,
				Product:      attributes.product,
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
	serial       string
	manufacturer string
	product      string
	deviceClass  string
	busNumber    int
	deviceNumber int
}

// optionalAttributeNames are descriptors a device may simply not publish. They
// name the device for an operator and, for the serial, tell two units of the
// same product apart, so they are read where present and never required.
var optionalAttributeNames = []string{"serial", "manufacturer", "product", "bDeviceClass"}

func readUSBAttributes(directory string) (usbAttributes, bool, error) {
	attributeNames := []string{"idVendor", "idProduct", "busnum", "devnum"}
	values := make(map[string]string, len(attributeNames)+len(optionalAttributeNames))
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
	for _, name := range optionalAttributeNames {
		content, err := os.ReadFile(filepath.Join(directory, name))
		if err != nil {
			continue
		}
		values[name] = strings.TrimSpace(string(content))
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
		serial:       values["serial"],
		manufacturer: values["manufacturer"],
		product:      values["product"],
		deviceClass:  strings.ToLower(values["bDeviceClass"]),
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
