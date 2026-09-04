package system

import (
	"errors"
	"os"
	"reflect"
	"strings"
	"testing"
)

func TestReleaseArtifactName(t *testing.T) {
	if value := ArtifactName("0.1.0", "linux-armv6"); value != "carhibou-agent-0.1.0-linux-armv6" {
		t.Fatal(value)
	}
}

func TestServiceAlwaysRestartsAndUsesSystemdWatchdog(t *testing.T) {
	unit := serviceUnit()
	for _, line := range []string{"Restart=always", "RestartSec=10", "WatchdogSec=90"} {
		if !strings.Contains(unit, line) {
			t.Fatalf("service unit is missing %q:\n%s", line, unit)
		}
	}
	if strings.Contains(unit, "NotifyAccess=none") {
		t.Fatalf("service unit disables watchdog notifications:\n%s", unit)
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

func TestSIMComUdevRuleIsNarrowlyScoped(t *testing.T) {
	rule := simcomUdevRule()
	lines := strings.Split(strings.TrimSpace(rule), "\n")
	if len(lines) != 4 {
		t.Fatalf("rule has %d lines:\n%s", len(lines), rule)
	}
	for _, line := range lines[1:] {
		for _, scope := range []string{
			`SUBSYSTEM=="usb"`,
			`ENV{DEVTYPE}=="usb_device"`,
		} {
			if !strings.Contains(line, scope) {
				t.Errorf("rule line is missing scope %q: %s", scope, line)
			}
		}
		if !strings.Contains(line, `ATTR{idVendor}=="1e0e"`) && !strings.Contains(line, `ATTR{idVendor}=="0403"`) {
			t.Errorf("rule line allows an unexpected vendor: %s", line)
		}
	}
	if !strings.Contains(lines[1], `GROUP="carhibou-agent"`) || !strings.Contains(lines[1], `MODE="0660"`) ||
		!strings.Contains(lines[3], `ATTR{idVendor}=="0403"`) {
		t.Errorf("device permission rule is incomplete: %s", lines[1])
	}
	if !strings.Contains(lines[2], `ATTR{power/control}="on"`) {
		t.Errorf("autosuspend rule is incomplete: %s", lines[2])
	}
	for _, forbidden := range []string{`SUBSYSTEM=="tty"`, `MODE="0666"`, `TAG+="uaccess"`} {
		if strings.Contains(rule, forbidden) {
			t.Errorf("rule contains broad permission %q:\n%s", forbidden, rule)
		}
	}
}

func TestInstallSIMComUdevRuleWritesAndRefreshesOnlyMatchingUSBDevices(t *testing.T) {
	recorder := &udevRecorder{}
	path := "/test/rules.d/carhibou.rules"
	if err := installSIMComUdevRule(recorder.operations(), path); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(recorder.writes, []string{path}) {
		t.Fatalf("writes = %v", recorder.writes)
	}
	if string(recorder.writeData) != simcomUdevRule() {
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
		{"udevadm", "trigger", "--settle", "--subsystem-match=usb", "--attr-match=idVendor=1e0e", "--action=change"},
		{"udevadm", "trigger", "--settle", "--subsystem-match=usb", "--attr-match=idVendor=0403", "--action=change"},
	}
	if !reflect.DeepEqual(recorder.commands, wantCommands) {
		t.Fatalf("commands = %#v", recorder.commands)
	}
}

func TestInstallSIMComUdevRuleStopsAfterWriteOrRefreshFailure(t *testing.T) {
	writeFailure := &udevRecorder{writeErr: errors.New("read-only")}
	if err := installSIMComUdevRule(writeFailure.operations(), "/rule"); err == nil || !strings.Contains(err.Error(), "install SIMCom udev rule") {
		t.Fatalf("write error = %v", err)
	}
	if len(writeFailure.chmods) != 0 || len(writeFailure.commands) != 0 {
		t.Fatalf("continued after write failure: %#v", writeFailure)
	}

	commandFailure := &udevRecorder{commandErrAt: 1}
	if err := installSIMComUdevRule(commandFailure.operations(), "/rule"); err == nil || !strings.Contains(err.Error(), "command failed") {
		t.Fatalf("command error = %v", err)
	}
	if len(commandFailure.commands) != 1 {
		t.Fatalf("commands after failure = %#v", commandFailure.commands)
	}
}

func TestUninstallSIMComUdevRuleRemovesOwnedFileAndRefreshes(t *testing.T) {
	recorder := &udevRecorder{}
	path := "/test/rules.d/carhibou.rules"
	if err := uninstallSIMComUdevRule(recorder.operations(), path); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(recorder.removes, []string{path}) {
		t.Fatalf("removes = %v", recorder.removes)
	}
	if len(recorder.commands) != 3 {
		t.Fatalf("commands = %#v", recorder.commands)
	}
}

func TestUninstallSIMComUdevRuleIsIdempotent(t *testing.T) {
	recorder := &udevRecorder{removeErr: &os.PathError{Op: "remove", Path: "/rule", Err: os.ErrNotExist}}
	if err := uninstallSIMComUdevRule(recorder.operations(), "/rule"); err != nil {
		t.Fatal(err)
	}
	if len(recorder.commands) != 0 {
		t.Fatalf("commands = %#v", recorder.commands)
	}
}
