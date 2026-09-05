package system

import (
	"errors"
	"os"
	"reflect"
	"strings"
	"testing"

	"github.com/Buco7854/carhibou/agent/internal/usbrecovery"
)

func TestReleaseArtifactName(t *testing.T) {
	if value := ArtifactName("0.1.0", "linux-armv6"); value != "carhibou-agent-0.1.0-linux-armv6" {
		t.Fatal(value)
	}
}

func TestServiceAlwaysRestartsAndUsesSystemdWatchdog(t *testing.T) {
	unit := serviceUnit()
	for _, line := range []string{"Restart=always", "RestartSec=10", "WatchdogSec=90", "NotifyAccess=main"} {
		if !strings.Contains(unit, line) {
			t.Fatalf("service unit is missing %q:\n%s", line, unit)
		}
	}
}

func TestUpdateServiceUnitWritesCurrentUnitAndReloadsSystemd(t *testing.T) {
	recorder := &udevRecorder{}
	path := "/etc/systemd/system/" + ServiceName
	if err := writeServiceUnit(recorder.operations(), path); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(recorder.writes, []string{path}) {
		t.Fatalf("unit writes=%v, want [%s]", recorder.writes, path)
	}
	if string(recorder.writeData) != serviceUnit() || recorder.writeMode != 0o644 {
		t.Fatalf("written unit mode=%o content=%q", recorder.writeMode, recorder.writeData)
	}
	if !reflect.DeepEqual(recorder.commands, [][]string{{"systemctl", "daemon-reload"}}) {
		t.Fatalf("commands=%v", recorder.commands)
	}
}

type udevRecorder struct {
	writes       []string
	writeData    []byte
	writeMode    os.FileMode
	chmods       []string
	chmodMode    os.FileMode
	removes      []string
	commands     [][]string
	writeErr     error
	chmodErr     error
	removeErr    error
	commandErrAt int
}

func (recorder *udevRecorder) operations() udevOperations {
	return udevOperations{
		writeFile: func(path string, data []byte, mode os.FileMode) error {
			recorder.writes = append(recorder.writes, path)
			recorder.writeData = append([]byte(nil), data...)
			recorder.writeMode = mode
			return recorder.writeErr
		},
		chmod: func(path string, mode os.FileMode) error {
			recorder.chmods = append(recorder.chmods, path)
			recorder.chmodMode = mode
			return recorder.chmodErr
		},
		remove: func(path string) error {
			recorder.removes = append(recorder.removes, path)
			return recorder.removeErr
		},
		run: func(name string, args ...string) ([]byte, error) {
			recorder.commands = append(recorder.commands, append([]string{name}, args...))
			if recorder.commandErrAt == len(recorder.commands) {
				return []byte("command failed"), errors.New("exit status 1")
			}
			return nil, nil
		},
	}
}

// The rule names the devices the agent was configured with, whatever they are.
// Every earlier version listed makes — SIMCom, then FTDI, then FTDI narrowed by
// ScanTool's manufacturer string — and each narrowing was another guess about
// which parts the owner happened to own.
func TestUdevRuleGrantsOnlyTheConfiguredDevices(t *testing.T) {
	configured := []usbrecovery.DeviceID{
		{VendorID: "1e0e", ProductID: "9001", Serial: "0123456789"},
		{VendorID: "0403", ProductID: "6015"},
	}
	rule := usbRecoveryRule(configured)
	lines := strings.Split(strings.TrimSpace(rule), "\n")
	if len(lines) != 1+2*len(configured) {
		t.Fatalf("rule has %d lines:\n%s", len(lines), rule)
	}
	for _, line := range lines[1:] {
		for _, scope := range []string{`SUBSYSTEM=="usb"`, `ENV{DEVTYPE}=="usb_device"`, `ATTR{idProduct}==`} {
			if !strings.Contains(line, scope) {
				t.Errorf("rule line is missing scope %q: %s", scope, line)
			}
		}
	}
	for _, want := range []string{
		`ATTR{idVendor}=="1e0e", ATTR{idProduct}=="9001", ATTR{serial}=="0123456789", GROUP="carhibou-agent", MODE="0660"`,
		`ATTR{idVendor}=="1e0e", ATTR{idProduct}=="9001", ATTR{serial}=="0123456789", TEST=="power/control", ATTR{power/control}="on"`,
		`ATTR{idVendor}=="0403", ATTR{idProduct}=="6015", GROUP="carhibou-agent", MODE="0660"`,
		`ATTR{idVendor}=="0403", ATTR{idProduct}=="6015", TEST=="power/control", ATTR{power/control}="on"`,
	} {
		if !strings.Contains(rule, want) {
			t.Errorf("rule is missing %q:\n%s", want, rule)
		}
	}
	// A device with no serial is matched by product alone, so a rule for it must
	// not carry an empty serial match that nothing can satisfy.
	if strings.Contains(rule, `ATTR{serial}==""`) {
		t.Errorf("a device without a serial was pinned to an empty one:\n%s", rule)
	}
	for _, forbidden := range []string{`SUBSYSTEM=="tty"`, `MODE="0666"`, `TAG+="uaccess"`, "ScanTool"} {
		if strings.Contains(rule, forbidden) {
			t.Errorf("rule contains %q:\n%s", forbidden, rule)
		}
	}
}

func TestInstallUdevRuleWritesAndRefreshesOnlyTheConfiguredDevices(t *testing.T) {
	recorder := &udevRecorder{}
	path := "/test/rules.d/carhibou.rules"
	configured := []usbrecovery.DeviceID{
		{VendorID: "1e0e", ProductID: "9001"},
		{VendorID: "0403", ProductID: "6015"},
	}
	if err := installUdevRule(recorder.operations(), path, configured); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(recorder.writes, []string{path}) {
		t.Fatalf("writes = %v", recorder.writes)
	}
	if string(recorder.writeData) != usbRecoveryRule(configured) {
		t.Fatalf("written rule = %q", recorder.writeData)
	}
	if recorder.writeMode != 0o644 || recorder.chmodMode != 0o644 {
		t.Fatalf("modes = write %o, chmod %o", recorder.writeMode, recorder.chmodMode)
	}
	if !reflect.DeepEqual(recorder.chmods, []string{path}) {
		t.Fatalf("chmods = %v", recorder.chmods)
	}
	wantCommands := [][]string{
		{"udevadm", "control", "--reload-rules"},
		{
			"udevadm", "trigger", "--settle", "--subsystem-match=usb",
			"--attr-match=idVendor=1e0e", "--attr-match=idProduct=9001", "--action=change",
		},
		{
			"udevadm", "trigger", "--settle", "--subsystem-match=usb",
			"--attr-match=idVendor=0403", "--attr-match=idProduct=6015", "--action=change",
		},
	}
	if !reflect.DeepEqual(recorder.commands, wantCommands) {
		t.Fatalf("commands = %#v", recorder.commands)
	}
}

// Writing a rule with nothing in it would revoke the rights a working
// installation already has, which is worse than leaving them alone and saying so.
func TestInstallUdevRuleRefusesToWriteAnEmptyRule(t *testing.T) {
	recorder := &udevRecorder{}
	if err := installUdevRule(recorder.operations(), "/rule", nil); err == nil {
		t.Fatal("an empty device list was written as a rule")
	}
	if len(recorder.writes) != 0 || len(recorder.commands) != 0 {
		t.Fatalf("touched udev with nothing to grant: %#v", recorder)
	}
}

func TestInstallUdevRuleStopsAfterWriteOrRefreshFailure(t *testing.T) {
	configured := []usbrecovery.DeviceID{{VendorID: "1e0e", ProductID: "9001"}}
	writeFailure := &udevRecorder{writeErr: errors.New("read-only")}
	err := installUdevRule(writeFailure.operations(), "/rule", configured)
	if err == nil || !strings.Contains(err.Error(), "install USB recovery udev rule") {
		t.Fatalf("write error = %v", err)
	}
	if len(writeFailure.chmods) != 0 || len(writeFailure.commands) != 0 {
		t.Fatalf("continued after write failure: %#v", writeFailure)
	}

	commandFailure := &udevRecorder{commandErrAt: 1}
	err = installUdevRule(commandFailure.operations(), "/rule", configured)
	if err == nil || !strings.Contains(err.Error(), "command failed") {
		t.Fatalf("command error = %v", err)
	}
	if len(commandFailure.commands) != 1 {
		t.Fatalf("commands after failure = %#v", commandFailure.commands)
	}
}

func TestUninstallUdevRuleRemovesOwnedFileAndRefreshes(t *testing.T) {
	recorder := &udevRecorder{}
	path := "/test/rules.d/carhibou.rules"
	if err := uninstallUdevRule(recorder.operations(), path); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(recorder.removes, []string{path}) {
		t.Fatalf("removes = %v", recorder.removes)
	}
	// The rule is gone and with it the record of which devices it named, so the
	// refresh is the whole subsystem.
	wantCommands := [][]string{
		{"udevadm", "control", "--reload-rules"},
		{"udevadm", "trigger", "--settle", "--subsystem-match=usb", "--action=change"},
	}
	if !reflect.DeepEqual(recorder.commands, wantCommands) {
		t.Fatalf("commands = %#v", recorder.commands)
	}
}

func TestUninstallUdevRuleIsIdempotent(t *testing.T) {
	recorder := &udevRecorder{removeErr: &os.PathError{Op: "remove", Path: "/rule", Err: os.ErrNotExist}}
	if err := uninstallUdevRule(recorder.operations(), "/rule"); err != nil {
		t.Fatal(err)
	}
	if len(recorder.commands) != 0 {
		t.Fatalf("commands = %#v", recorder.commands)
	}
}
