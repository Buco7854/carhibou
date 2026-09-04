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

func (tree *fakeUSBTree) recovery() *Recovery {
	return New(Config{
		SysClassTTYRoot: tree.sysClassTTY,
		USBBusRoot:      tree.usbBusRoot,
		Reset: func(path string) error {
			tree.resetPaths = append(tree.resetPaths, path)
			return tree.resetError
		},
	})
}

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

func TestResetTTYResolvesSIMComPhysicalDevice(t *testing.T) {
	tree := newFakeUSBTree(t)
	tree.addUSBDevice("1-1", "", "1E0E", "9011", "1", "7")
	tty := tree.addTTY("ttyUSB3", "1-1", 3)

	device, err := tree.recovery().ResetTTY(tty)
	if err != nil {
		t.Fatal(err)
	}
	wantPath := filepath.Join(tree.usbBusRoot, "001", "007")
	if device.VendorID != SIMComVendorID || device.ProductID != "9011" || device.BusNumber != 1 || device.DeviceNumber != 7 || device.Path != wantPath {
		t.Fatalf("unexpected resolved device: %+v", device)
	}
	if len(tree.resetPaths) != 1 || tree.resetPaths[0] != wantPath {
		t.Fatalf("reset paths = %v, want [%s]", tree.resetPaths, wantPath)
	}
}

func TestFTDIResetRequiresExplicitRecoveryPolicy(t *testing.T) {
	tree := newFakeUSBTree(t)
	tree.addUSBDevice("1-2", "", FTDIVendorID, "6015", "1", "8")
	tty := tree.addTTY("ttyUSB0", "1-2", 0)
	if _, err := tree.recovery().ResetTTY(tty); !errors.Is(err, ErrUnsupported) {
		t.Fatalf("default recovery accepted FTDI: %v", err)
	}
	recovery := New(Config{
		SysClassTTYRoot:  tree.sysClassTTY,
		USBBusRoot:       tree.usbBusRoot,
		AllowedVendorIDs: []string{FTDIVendorID},
		Reset: func(path string) error {
			tree.resetPaths = append(tree.resetPaths, path)
			return nil
		},
	})
	if _, err := recovery.ResetTTY(tty); err != nil {
		t.Fatal(err)
	}
}

func TestResetTTYAcceptsStableDevSymlink(t *testing.T) {
	tree := newFakeUSBTree(t)
	tree.addUSBDevice("1-2", "", SIMComVendorID, "9001", "2", "12")
	tty := tree.addTTY("ttyUSB0", "1-2", 0)
	stableDirectory := filepath.Join(tree.devRoot, "serial", "by-id")
	tree.mkdir(stableDirectory)
	stable := filepath.Join(stableDirectory, "usb-SimTech_SIM7600-if00-port0")
	if err := os.Symlink(tty, stable); err != nil {
		t.Fatal(err)
	}

	device, err := tree.recovery().ResetTTY(stable)
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
	tree.addUSBDevice("1-4", "", SIMComVendorID, "9011", "1", "4")
	modem := tree.addTTY("ttyUSB1", "1-4", 2)
	sameModem := tree.addTTY("ttyUSB2", "1-4", 3)
	tree.addUSBDevice("1-5", "", SIMComVendorID, "9001", "1", "5")
	secondModem := tree.addTTY("ttyUSB4", "1-5", 0)

	missing := filepath.Join(tree.devRoot, "ttyUSB99")
	device, err := tree.recovery().ResetCandidates([]string{missing, ftdi, modem, sameModem, secondModem})
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

func TestResetTTYRefusesFTDIWithoutReset(t *testing.T) {
	tree := newFakeUSBTree(t)
	tree.addUSBDevice("1-3", "", "0403", "6001", "1", "3")
	tty := tree.addTTY("ttyUSB0", "1-3", 0)

	_, err := tree.recovery().ResetTTY(tty)
	if !errors.Is(err, ErrUnsupported) {
		t.Fatalf("error = %v, want ErrUnsupported", err)
	}
	if len(tree.resetPaths) != 0 {
		t.Fatalf("reset unexpectedly invoked for FTDI: %v", tree.resetPaths)
	}
}

func TestResetTTYRefusesRootHubWithoutReset(t *testing.T) {
	tree := newFakeUSBTree(t)
	tree.addUSBDevice("usb1", "", "1d6b", "0002", "1", "1")
	tty := tree.addTTY("ttyUSB0", "usb1", 0)

	_, err := tree.recovery().ResetTTY(tty)
	if !errors.Is(err, ErrUnsupported) {
		t.Fatalf("error = %v, want ErrUnsupported", err)
	}
	if len(tree.resetPaths) != 0 {
		t.Fatalf("reset unexpectedly invoked for root hub: %v", tree.resetPaths)
	}
}

func TestResetTTYNeverSkipsNearestUSBDevice(t *testing.T) {
	tree := newFakeUSBTree(t)
	tree.addUSBDevice("simcom-parent", "", SIMComVendorID, "9011", "1", "2")
	tree.addUSBDevice("ftdi-child", "simcom-parent", "0403", "6001", "1", "3")
	tty := tree.addTTY("ttyUSB0", "ftdi-child", 0)

	_, err := tree.recovery().ResetTTY(tty)
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

	_, err := tree.recovery().ResetTTY(tty)
	if !errors.Is(err, ErrUnsupported) {
		t.Fatalf("error = %v, want ErrUnsupported", err)
	}
	if len(tree.resetPaths) != 0 {
		t.Fatalf("reset unexpectedly invoked for platform tty: %v", tree.resetPaths)
	}
}

func TestResetTTYReportsMissingCandidate(t *testing.T) {
	tree := newFakeUSBTree(t)
	_, err := tree.recovery().ResetTTY(filepath.Join(tree.devRoot, "ttyUSB99"))
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
	if _, err := tree.recovery().ResetCandidates([]string{missing}); !errors.Is(err, ErrNotFound) {
		t.Fatalf("all-missing error = %v, want ErrNotFound", err)
	}

	tree.addUSBDevice("1-6", "", "0403", "6001", "1", "6")
	ftdi := tree.addTTY("ttyUSB0", "1-6", 0)
	if _, err := tree.recovery().ResetCandidates([]string{missing, ftdi}); !errors.Is(err, ErrUnsupported) {
		t.Fatalf("unsupported error = %v, want ErrUnsupported", err)
	}
}

func TestResetTTYRejectsIncompleteUSBIdentity(t *testing.T) {
	tree := newFakeUSBTree(t)
	physical := tree.addUSBDevice("1-7", "", SIMComVendorID, "9011", "1", "7")
	if err := os.Remove(filepath.Join(physical, "devnum")); err != nil {
		t.Fatal(err)
	}
	tty := tree.addTTY("ttyUSB0", "1-7", 0)

	_, err := tree.recovery().ResetTTY(tty)
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
			physical := tree.addUSBDevice("1-8", "", SIMComVendorID, "9011", "1", "8")
			tree.write(filepath.Join(physical, test.field), test.value)
			tty := tree.addTTY("ttyUSB0", "1-8", 0)

			_, err := tree.recovery().ResetTTY(tty)
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
			tree.addUSBDevice("1-9", "", SIMComVendorID, "9011", "3", "9")
			tty := tree.addTTY("ttyUSB0", "1-9", 0)
			tree.resetError = permissionError

			device, err := tree.recovery().ResetTTY(tty)
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
	tree.addUSBDevice("1-10", "", SIMComVendorID, "9011", "4", "10")
	tty := tree.addTTY("ttyUSB0", "1-10", 0)
	operationError := errors.New("device disappeared")
	tree.resetError = operationError

	device, err := tree.recovery().ResetTTY(tty)
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
