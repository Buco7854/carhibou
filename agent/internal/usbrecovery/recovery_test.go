package usbrecovery

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
)

type fakeUSBTree struct {
	t             *testing.T
	root          string
	sysClassTTY   string
	sysDevices    string
	devRoot       string
	usbBusRoot    string
	resetPaths    []string
	resetError    error
	physicalPaths map[string]string
}

func newFakeUSBTree(t *testing.T) *fakeUSBTree {
	t.Helper()
	root := t.TempDir()
	tree := &fakeUSBTree{
		t:             t,
		root:          root,
		sysClassTTY:   filepath.Join(root, "sys", "class", "tty"),
		sysDevices:    filepath.Join(root, "sys", "devices", "pci0000:00", "usb1"),
		devRoot:       filepath.Join(root, "dev"),
		usbBusRoot:    filepath.Join(root, "dev", "bus", "usb"),
		physicalPaths: make(map[string]string),
	}
	tree.mkdir(tree.sysClassTTY)
	tree.mkdir(tree.sysDevices)
	tree.mkdir(tree.devRoot)
	return tree
}

// recovery allows exactly the devices named, the way the agent allows the ones
// its configured ttys resolve to.
func (tree *fakeUSBTree) recovery(allowed ...DeviceID) *Recovery {
	return New(Config{
		SysClassTTYRoot: tree.sysClassTTY,
		USBBusRoot:      tree.usbBusRoot,
		AllowedDevices:  allowed,
		Reset: func(path string) error {
			tree.resetPaths = append(tree.resetPaths, path)
			return tree.resetError
		},
	})
}

func (tree *fakeUSBTree) setAttributes(name string, attributes map[string]string) {
	tree.t.Helper()
	for attribute, value := range attributes {
		tree.write(filepath.Join(tree.physicalPaths[name], attribute), value+"\n")
	}
}

var (
	simcom9011 = DeviceID{VendorID: "1e0e", ProductID: "9011"}
	simcom9001 = DeviceID{VendorID: "1e0e", ProductID: "9001"}
	ftdi6015   = DeviceID{VendorID: "0403", ProductID: "6015"}
	ftdi6001   = DeviceID{VendorID: "0403", ProductID: "6001"}
)

func (tree *fakeUSBTree) addUSBDevice(name, parent, vendor, product, bus, device string) string {
	tree.t.Helper()
	directory := filepath.Join(tree.sysDevices, name)
	if parent != "" {
		directory = filepath.Join(tree.physicalPaths[parent], name)
	}
	tree.mkdir(directory)
	tree.write(filepath.Join(directory, "idVendor"), vendor+"\n")
	tree.write(filepath.Join(directory, "idProduct"), product+"\n")
	tree.write(filepath.Join(directory, "busnum"), bus+"\n")
	tree.write(filepath.Join(directory, "devnum"), device+"\n")
	tree.physicalPaths[name] = directory
	return directory
}

func (tree *fakeUSBTree) addTTY(name, usbDevice string, interfaceNumber int) string {
	tree.t.Helper()
	physical := tree.physicalPaths[usbDevice]
	interfacePath := filepath.Join(physical, fmt.Sprintf("%s:1.%d", usbDevice, interfaceNumber))
	ttyPath := filepath.Join(interfacePath, "tty", name)
	tree.mkdir(ttyPath)
	classPath := filepath.Join(tree.sysClassTTY, name)
	tree.mkdir(classPath)
	if err := os.Symlink(ttyPath, filepath.Join(classPath, "device")); err != nil {
		tree.t.Fatal(err)
	}
	devicePath := filepath.Join(tree.devRoot, name)
	tree.write(devicePath, "")
	return devicePath
}

func (tree *fakeUSBTree) addNonUSBTTY(name string) string {
	tree.t.Helper()
	ttyPath := filepath.Join(tree.root, "sys", "devices", "platform", "serial", name)
	tree.mkdir(ttyPath)
	classPath := filepath.Join(tree.sysClassTTY, name)
	tree.mkdir(classPath)
	if err := os.Symlink(ttyPath, filepath.Join(classPath, "device")); err != nil {
		tree.t.Fatal(err)
	}
	devicePath := filepath.Join(tree.devRoot, name)
	tree.write(devicePath, "")
	return devicePath
}

func (tree *fakeUSBTree) mkdir(path string) {
	tree.t.Helper()
	if err := os.MkdirAll(path, 0o755); err != nil {
		tree.t.Fatal(err)
	}
}

func (tree *fakeUSBTree) write(path, content string) {
	tree.t.Helper()
	tree.mkdir(filepath.Dir(path))
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		tree.t.Fatal(err)
	}
}

func TestResetTTYResolvesTheConfiguredPhysicalDevice(t *testing.T) {
	tree := newFakeUSBTree(t)
	tree.addUSBDevice("1-1", "", "1E0E", "9011", "1", "7")
	tty := tree.addTTY("ttyUSB3", "1-1", 3)

	device, err := tree.recovery(simcom9011).ResetTTY(tty)
	if err != nil {
		t.Fatal(err)
	}
	wantPath := filepath.Join(tree.usbBusRoot, "001", "007")
	if device.VendorID != "1e0e" || device.ProductID != "9011" || device.BusNumber != 1 || device.DeviceNumber != 7 || device.Path != wantPath {
		t.Fatalf("unexpected resolved device: %+v", device)
	}
	if len(tree.resetPaths) != 1 || tree.resetPaths[0] != wantPath {
		t.Fatalf("reset paths = %v, want [%s]", tree.resetPaths, wantPath)
	}
}

// Reset rights follow the devices the agent was configured with, not a list of
// parts written into the program. The same adapter is refused or accepted purely
// by whether it is one of them, and a sibling product of the same vendor is not.
func TestResetRequiresTheDeviceToBeOneOfTheConfiguredOnes(t *testing.T) {
	tree := newFakeUSBTree(t)
	tree.addUSBDevice("1-2", "", "0403", "6015", "1", "8")
	tty := tree.addTTY("ttyUSB0", "1-2", 0)

	if _, err := tree.recovery(simcom9011).ResetTTY(tty); !errors.Is(err, ErrUnsupported) {
		t.Fatalf("an unconfigured device was reset: %v", err)
	}
	if _, err := tree.recovery(ftdi6001).ResetTTY(tty); !errors.Is(err, ErrUnsupported) {
		t.Fatalf("another product of the same vendor was accepted: %v", err)
	}
	if len(tree.resetPaths) != 0 {
		t.Fatalf("reset invoked for an unconfigured device: %v", tree.resetPaths)
	}
	if _, err := tree.recovery(ftdi6015).ResetTTY(tty); err != nil {
		t.Fatal(err)
	}
	if len(tree.resetPaths) != 1 {
		t.Fatalf("reset paths=%v, want the configured device reset once", tree.resetPaths)
	}
}

// Two units of one product are told apart by the serial they publish, and a
// device that publishes none is matched by product alone rather than refused.
func TestConfiguredSerialSelectsBetweenIdenticalDevices(t *testing.T) {
	tree := newFakeUSBTree(t)
	tree.addUSBDevice("1-1", "", "0403", "6015", "1", "4")
	tree.setAttributes("1-1", map[string]string{"serial": "SX-ONE", "manufacturer": "ScanTool.net LLC"})
	first := tree.addTTY("ttyUSB0", "1-1", 0)
	tree.addUSBDevice("1-2", "", "0403", "6015", "1", "5")
	tree.setAttributes("1-2", map[string]string{"serial": "SX-TWO"})
	second := tree.addTTY("ttyUSB1", "1-2", 0)

	configured := DeviceID{VendorID: "0403", ProductID: "6015", Serial: "SX-ONE"}
	if _, err := tree.recovery(configured).ResetTTY(second); !errors.Is(err, ErrUnsupported) {
		t.Fatalf("the other unit of the same product was reset: %v", err)
	}
	device, err := tree.recovery(configured).ResetTTY(first)
	if err != nil {
		t.Fatal(err)
	}
	if device.Serial != "SX-ONE" || device.Manufacturer != "ScanTool.net LLC" {
		t.Fatalf("descriptors lost: %+v", device)
	}
	if _, err := tree.recovery(ftdi6015).ResetTTY(second); err != nil {
		t.Fatalf("a product-only selection refused a unit: %v", err)
	}
}

// Identify is how the allowed set is built, so it cannot be gated by it; it
// still refuses a hub, and it carries the descriptor strings an operator needs
// when nothing the agent was configured with could be found.
func TestIdentifyNamesTheDeviceWithoutConsultingTheAllowedSet(t *testing.T) {
	tree := newFakeUSBTree(t)
	tree.addUSBDevice("1-1", "", "1E0E", "9011", "1", "7")
	tree.setAttributes("1-1", map[string]string{"manufacturer": "SimTech", "product": "SIM7600", "serial": "0123"})
	tty := tree.addTTY("ttyUSB2", "1-1", 2)

	device, err := tree.recovery().Identify(tty)
	if err != nil {
		t.Fatal(err)
	}
	if device.ID() != (DeviceID{VendorID: "1e0e", ProductID: "9011", Serial: "0123"}) {
		t.Fatalf("identity=%+v", device.ID())
	}
	for _, descriptor := range []string{"1e0e:9011", `"SimTech"`, `"SIM7600"`, "serial 0123"} {
		if !strings.Contains(device.String(), descriptor) {
			t.Fatalf("description %q is missing %s", device.String(), descriptor)
		}
	}
	if len(tree.resetPaths) != 0 {
		t.Fatalf("identifying a device reset it: %v", tree.resetPaths)
	}
}

func TestResetTTYAcceptsStableDevSymlink(t *testing.T) {
	tree := newFakeUSBTree(t)
	tree.addUSBDevice("1-2", "", "1e0e", "9001", "2", "12")
	tty := tree.addTTY("ttyUSB0", "1-2", 0)
	stableDirectory := filepath.Join(tree.devRoot, "serial", "by-id")
	tree.mkdir(stableDirectory)
	stable := filepath.Join(stableDirectory, "usb-SimTech_SIM7600-if00-port0")
	if err := os.Symlink(tty, stable); err != nil {
		t.Fatal(err)
	}

	device, err := tree.recovery(simcom9001).ResetTTY(stable)
	if err != nil {
		t.Fatal(err)
	}
	if device.ProductID != "9001" {
		t.Fatalf("product ID = %q", device.ProductID)
	}
}

func TestResetCandidatesUsesPriorityAndResetsOnce(t *testing.T) {
	tree := newFakeUSBTree(t)
	tree.addUSBDevice("1-3", "", "0403", "6001", "1", "3")
	ftdi := tree.addTTY("ttyUSB0", "1-3", 0)
	tree.addUSBDevice("1-4", "", "1e0e", "9011", "1", "4")
	modem := tree.addTTY("ttyUSB1", "1-4", 2)
	sameModem := tree.addTTY("ttyUSB2", "1-4", 3)
	tree.addUSBDevice("1-5", "", "1e0e", "9001", "1", "5")
	secondModem := tree.addTTY("ttyUSB4", "1-5", 0)

	missing := filepath.Join(tree.devRoot, "ttyUSB99")
	device, err := tree.recovery(simcom9011, simcom9001).
		ResetCandidates([]string{missing, ftdi, modem, sameModem, secondModem})
	if err != nil {
		t.Fatal(err)
	}
	if device.DeviceNumber != 4 {
		t.Fatalf("reset device number = %d, want prioritized device 4", device.DeviceNumber)
	}
	if len(tree.resetPaths) != 1 {
		t.Fatalf("reset was invoked %d times, want once", len(tree.resetPaths))
	}
}

// A hub owns every tty below it, so it is refused even when it is named: a
// configuration that resolved to one would otherwise take down devices nobody
// asked about, including the root hub the agent's own modem hangs from.
func TestResetTTYRefusesAHubEvenWhenItIsConfigured(t *testing.T) {
	tree := newFakeUSBTree(t)
	tree.addUSBDevice("usb1", "", "1d6b", "0002", "1", "1")
	tree.setAttributes("usb1", map[string]string{"bDeviceClass": "09"})
	tty := tree.addTTY("ttyUSB0", "usb1", 0)

	_, err := tree.recovery(DeviceID{VendorID: "1d6b", ProductID: "0002"}).ResetTTY(tty)
	if !errors.Is(err, ErrUnsupported) {
		t.Fatalf("error = %v, want ErrUnsupported", err)
	}
	if len(tree.resetPaths) != 0 {
		t.Fatalf("reset unexpectedly invoked for root hub: %v", tree.resetPaths)
	}
}

func TestResetTTYNeverSkipsNearestUSBDevice(t *testing.T) {
	tree := newFakeUSBTree(t)
	tree.addUSBDevice("simcom-parent", "", "1e0e", "9011", "1", "2")
	tree.addUSBDevice("ftdi-child", "simcom-parent", "0403", "6001", "1", "3")
	tty := tree.addTTY("ttyUSB0", "ftdi-child", 0)

	_, err := tree.recovery(simcom9011).ResetTTY(tty)
	if !errors.Is(err, ErrUnsupported) || !strings.Contains(err.Error(), "0403") {
		t.Fatalf("error = %v, want nearest FTDI rejection", err)
	}
	if len(tree.resetPaths) != 0 {
		t.Fatalf("reset unexpectedly climbed to SIMCom parent: %v", tree.resetPaths)
	}
}

func TestResetTTYRefusesNonUSBTTY(t *testing.T) {
	tree := newFakeUSBTree(t)
	tty := tree.addNonUSBTTY("ttyAMA0")

	_, err := tree.recovery(simcom9011).ResetTTY(tty)
	if !errors.Is(err, ErrUnsupported) {
		t.Fatalf("error = %v, want ErrUnsupported", err)
	}
	if len(tree.resetPaths) != 0 {
		t.Fatalf("reset unexpectedly invoked for platform tty: %v", tree.resetPaths)
	}
}

func TestResetTTYReportsMissingCandidate(t *testing.T) {
	tree := newFakeUSBTree(t)
	_, err := tree.recovery(simcom9011).ResetTTY(filepath.Join(tree.devRoot, "ttyUSB99"))
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("error = %v, want ErrNotFound", err)
	}
	if errors.Is(err, ErrUnsupported) {
		t.Fatalf("missing tty was also classified unsupported: %v", err)
	}
}

func TestResetCandidatesDistinguishesAbsentFromUnsupported(t *testing.T) {
	tree := newFakeUSBTree(t)
	missing := filepath.Join(tree.devRoot, "ttyUSB99")
	if _, err := tree.recovery(simcom9011).ResetCandidates([]string{missing}); !errors.Is(err, ErrNotFound) {
		t.Fatalf("all-missing error = %v, want ErrNotFound", err)
	}

	tree.addUSBDevice("1-6", "", "0403", "6001", "1", "6")
	ftdi := tree.addTTY("ttyUSB0", "1-6", 0)
	if _, err := tree.recovery(simcom9011).ResetCandidates([]string{missing, ftdi}); !errors.Is(err, ErrUnsupported) {
		t.Fatalf("unsupported error = %v, want ErrUnsupported", err)
	}
}

func TestResetTTYRejectsIncompleteUSBIdentity(t *testing.T) {
	tree := newFakeUSBTree(t)
	physical := tree.addUSBDevice("1-7", "", "1e0e", "9011", "1", "7")
	if err := os.Remove(filepath.Join(physical, "devnum")); err != nil {
		t.Fatal(err)
	}
	tty := tree.addTTY("ttyUSB0", "1-7", 0)

	_, err := tree.recovery(simcom9011).ResetTTY(tty)
	if err == nil || !strings.Contains(err.Error(), "devnum is missing") {
		t.Fatalf("error = %v, want missing devnum", err)
	}
	if errors.Is(err, ErrUnsupported) || len(tree.resetPaths) != 0 {
		t.Fatalf("incomplete identity was treated as safe: error=%v resets=%v", err, tree.resetPaths)
	}
}

func TestResetTTYRejectsMalformedUSBIdentity(t *testing.T) {
	tests := []struct {
		name  string
		field string
		value string
	}{
		{name: "vendor", field: "idVendor", value: "simc"},
		{name: "product", field: "idProduct", value: "xyz"},
		{name: "bus", field: "busnum", value: "0"},
		{name: "device", field: "devnum", value: "not-a-number"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			tree := newFakeUSBTree(t)
			physical := tree.addUSBDevice("1-8", "", "1e0e", "9011", "1", "8")
			tree.write(filepath.Join(physical, test.field), test.value)
			tty := tree.addTTY("ttyUSB0", "1-8", 0)

			_, err := tree.recovery(simcom9011).ResetTTY(tty)
			if err == nil || !strings.Contains(err.Error(), "invalid") {
				t.Fatalf("error = %v, want invalid identity", err)
			}
			if len(tree.resetPaths) != 0 {
				t.Fatalf("reset invoked with malformed identity: %v", tree.resetPaths)
			}
		})
	}
}

func TestResetTTYClassifiesPermissionErrors(t *testing.T) {
	for _, permissionError := range []error{syscall.EACCES, syscall.EPERM} {
		t.Run(permissionError.Error(), func(t *testing.T) {
			tree := newFakeUSBTree(t)
			tree.addUSBDevice("1-9", "", "1e0e", "9011", "3", "9")
			tty := tree.addTTY("ttyUSB0", "1-9", 0)
			tree.resetError = permissionError

			device, err := tree.recovery(simcom9011).ResetTTY(tty)
			if !errors.Is(err, ErrPermission) || !errors.Is(err, permissionError) {
				t.Fatalf("error = %v, want ErrPermission wrapping %v", err, permissionError)
			}
			if device.ProductID != "9011" {
				t.Fatalf("resolved device lost on permission failure: %+v", device)
			}
		})
	}
}

func TestResetTTYClassifiesOtherResetFailure(t *testing.T) {
	tree := newFakeUSBTree(t)
	tree.addUSBDevice("1-10", "", "1e0e", "9011", "4", "10")
	tty := tree.addTTY("ttyUSB0", "1-10", 0)
	operationError := errors.New("device disappeared")
	tree.resetError = operationError

	device, err := tree.recovery(simcom9011).ResetTTY(tty)
	if !errors.Is(err, ErrReset) || !errors.Is(err, operationError) {
		t.Fatalf("error = %v, want ErrReset wrapping operation error", err)
	}
	if errors.Is(err, ErrPermission) {
		t.Fatalf("non-permission reset error misclassified: %v", err)
	}
	if device.Path == "" {
		t.Fatal("resolved device was not returned with reset error")
	}
}
