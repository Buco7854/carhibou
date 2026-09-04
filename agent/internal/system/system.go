package system

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"os/exec"
	"os/user"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"

	"github.com/Buco7854/carhibou/agent/internal/client"
	"github.com/Buco7854/carhibou/agent/internal/store"
)

const (
	ServiceName        = "carhibou-agent.service"
	BinaryPath         = "/usr/local/bin/carhibou-agent"
	ConfigDir          = "/etc/carhibou-agent"
	DataDir            = "/var/lib/carhibou-agent"
	simcomUdevRulePath = "/etc/udev/rules.d/99-carhibou-agent-simcom.rules"
)

type udevOperations struct {
	writeFile func(string, []byte, os.FileMode) error
	chmod     func(string, os.FileMode) error
	remove    func(string) error
	run       func(string, ...string) ([]byte, error)
}

func hostUdevOperations() udevOperations {
	return udevOperations{
		writeFile: os.WriteFile,
		chmod:     os.Chmod,
		remove:    os.Remove,
		run: func(name string, args ...string) ([]byte, error) {
			return exec.Command(name, args...).CombinedOutput()
		},
	}
}

func RequireRoot() error {
	if os.Geteuid() != 0 {
		return fmt.Errorf("this command must run as root (use sudo)")
	}
	return nil
}

func SetupIdentityAndDirectories() error {
	if err := RequireRoot(); err != nil {
		return err
	}
	if exec.Command("getent", "group", "carhibou-agent").Run() != nil {
		if output, err := exec.Command("groupadd", "--system", "carhibou-agent").CombinedOutput(); err != nil {
			return fmt.Errorf("create service group: %s: %w", strings.TrimSpace(string(output)), err)
		}
	}
	if exec.Command("id", "carhibou-agent").Run() != nil {
		if output, err := exec.Command("useradd", "--system", "--gid", "carhibou-agent", "--home", DataDir, "--shell", "/usr/sbin/nologin", "carhibou-agent").CombinedOutput(); err != nil {
			return fmt.Errorf("create service user: %s: %w", strings.TrimSpace(string(output)), err)
		}
	}
	if exec.Command("getent", "group", "dialout").Run() == nil {
		if output, err := exec.Command("usermod", "--append", "--groups", "dialout", "carhibou-agent").CombinedOutput(); err != nil {
			return fmt.Errorf("grant serial access: %s: %w", strings.TrimSpace(string(output)), err)
		}
	}
	account, err := user.Lookup("carhibou-agent")
	if err != nil {
		return err
	}
	uid, err := strconv.Atoi(account.Uid)
	if err != nil {
		return err
	}
	gid, err := strconv.Atoi(account.Gid)
	if err != nil {
		return err
	}
	for _, path := range []string{ConfigDir, DataDir} {
		if err := os.MkdirAll(path, 0o750); err != nil {
			return err
		}
		if err := os.Chmod(path, 0o750); err != nil {
			return err
		}
		if err := os.Chown(path, uid, gid); err != nil {
			return err
		}
	}
	return nil
}

func ChownAgent(path string) error {
	account, err := user.Lookup("carhibou-agent")
	if err != nil {
		return err
	}
	uid, err := strconv.Atoi(account.Uid)
	if err != nil {
		return err
	}
	gid, err := strconv.Atoi(account.Gid)
	if err != nil {
		return err
	}
	return os.Chown(path, uid, gid)
}

// ServiceRunning reports whether the telemetry service is active.
//
// The service holds the serial ports it uses, and root opens them anyway because
// the exclusive-access flag does not apply to it, so a diagnostic run alongside
// the service has both processes reading the same stream and reconfiguring the
// same line settings underneath each other.
func ServiceRunning() bool {
	output, _ := exec.Command("systemctl", "is-active", ServiceName).Output()
	return strings.TrimSpace(string(output)) == "active"
}

func InstallService() error {
	unit := `[Unit]
Description=Carhibou vehicle telemetry agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=carhibou-agent
Group=carhibou-agent
ExecStart=/usr/local/bin/carhibou-agent run
Restart=always
RestartSec=10
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/carhibou-agent /etc/carhibou-agent

[Install]
WantedBy=multi-user.target
`
	warnIfSIMComUdevRuleUnavailable(installSIMComUdevRule(hostUdevOperations(), simcomUdevRulePath))
	if err := os.WriteFile("/etc/systemd/system/"+ServiceName, []byte(unit), 0o644); err != nil {
		return err
	}
	if output, err := exec.Command("systemctl", "daemon-reload").CombinedOutput(); err != nil {
		return fmt.Errorf("reload systemd: %s: %w", strings.TrimSpace(string(output)), err)
	}
	if output, err := exec.Command("systemctl", "enable", "--now", ServiceName).CombinedOutput(); err != nil {
		return fmt.Errorf("start service: %s: %w", strings.TrimSpace(string(output)), err)
	}
	return nil
}

func Uninstall(yes bool) error {
	if err := RequireRoot(); err != nil {
		return err
	}
	if !yes {
		fmt.Println("This removes the Carhibou service, credentials, local configuration, and queued telemetry.")
		fmt.Print("Type 'uninstall' to continue: ")
		answer, err := bufio.NewReader(os.Stdin).ReadString('\n')
		if err != nil {
			return fmt.Errorf("refusing non-interactive removal without --yes")
		}
		if strings.TrimSpace(answer) != "uninstall" {
			fmt.Println("Uninstall cancelled.")
			return nil
		}
	}
	ignoreCommand("systemctl", "disable", "--now", ServiceName)
	warnIfSIMComUdevRuleUnavailable(uninstallSIMComUdevRule(hostUdevOperations(), simcomUdevRulePath))
	if err := os.Remove("/etc/systemd/system/" + ServiceName); err != nil && !os.IsNotExist(err) {
		return err
	}
	ignoreCommand("systemctl", "daemon-reload")
	ignoreCommand("systemctl", "reset-failed", ServiceName)
	for _, path := range []string{ConfigDir, DataDir, "/opt/carhibou-agent", "/usr/local/bin/carhibou-agent-uninstall"} {
		if err := os.RemoveAll(path); err != nil {
			return err
		}
	}
	ignoreCommand("userdel", "carhibou-agent")
	ignoreCommand("groupdel", "carhibou-agent")
	if err := os.Remove(BinaryPath); err != nil && !os.IsNotExist(err) {
		return err
	}
	fmt.Println("Carhibou agent fully removed, including credentials and queued telemetry. Shared OS files were untouched.")
	return nil
}

func Update(api *client.Client, version, target string) error {
	if err := RequireRoot(); err != nil {
		return err
	}
	name := ArtifactName(version, target)
	base := "/agent/releases/" + version + "/" + name
	digestFile, err := api.Download(base+".sha256", false)
	if err != nil {
		return err
	}
	expected := strings.Fields(string(digestFile))
	if len(expected) == 0 || len(expected[0]) != sha256.Size*2 {
		return fmt.Errorf("release checksum is invalid")
	}
	binary, err := api.Download(base, false)
	if err != nil {
		return err
	}
	actual := sha256.Sum256(binary)
	if !strings.EqualFold(expected[0], hex.EncodeToString(actual[:])) {
		return fmt.Errorf("release checksum mismatch")
	}
	warnIfSIMComUdevRuleUnavailable(installSIMComUdevRule(hostUdevOperations(), simcomUdevRulePath))
	temporary, err := os.CreateTemp(filepath.Dir(BinaryPath), ".carhibou-agent-*")
	if err != nil {
		return err
	}
	path := temporary.Name()
	defer os.Remove(path)
	if err := temporary.Chmod(0o755); err != nil {
		temporary.Close()
		return err
	}
	if _, err := temporary.Write(binary); err != nil {
		temporary.Close()
		return err
	}
	if err := temporary.Sync(); err != nil {
		temporary.Close()
		return err
	}
	if err := temporary.Close(); err != nil {
		return err
	}
	if err := os.Rename(path, BinaryPath); err != nil {
		return err
	}
	if output, err := exec.Command("systemctl", "restart", ServiceName).CombinedOutput(); err != nil {
		return fmt.Errorf("restart service: %s: %w", strings.TrimSpace(string(output)), err)
	}
	return nil
}

func DetectTarget(buildTarget string) (string, error) {
	if buildTarget != "" && buildTarget != "dev" {
		return buildTarget, nil
	}
	switch runtime.GOARCH {
	case "amd64":
		return "linux-amd64", nil
	case "arm64":
		return "linux-arm64", nil
	case "arm":
		content, _ := os.ReadFile("/proc/cpuinfo")
		if strings.Contains(strings.ToLower(string(content)), "armv6") {
			return "linux-armv6", nil
		}
		return "linux-armv7", nil
	default:
		return "", fmt.Errorf("unsupported Linux architecture %s", runtime.GOARCH)
	}
}

func ArtifactName(version, target string) string {
	return fmt.Sprintf("carhibou-agent-%s-%s", version, target)
}

func LoadCredentials(path string) (store.Credentials, error) {
	var credentials store.Credentials
	if err := store.ReadJSON(path, &credentials); err != nil {
		return credentials, err
	}
	if credentials.ServerURL == "" || credentials.Credential == "" {
		return credentials, fmt.Errorf("credentials are incomplete")
	}
	return credentials, nil
}

// warnIfSIMComUdevRuleUnavailable reports a udev problem without failing the
// operation that hit it.
//
// The rule only grants the unprivileged service permission to reset a wedged
// SIMCom modem over usbfs, which is the last resort of position recovery and is
// reached after every AT-level remedy has failed. A host without udev, or one
// that refuses the trigger, still runs the agent perfectly well. Aborting an
// install or an update over it would trade the whole agent for its fallback.
func warnIfSIMComUdevRuleUnavailable(err error) {
	if err == nil {
		return
	}
	fmt.Fprintln(os.Stderr, "Warning: SIMCom USB recovery permissions were not configured:", err)
	fmt.Fprintln(os.Stderr, "The agent runs normally; recovering a wedged modem may need a manual replug.")
}

func simcomUdevRule() string {
	return `# Managed by Carhibou. Grants USB reset access only to SIMCom devices.
ACTION=="add|change", SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="1e0e", GROUP="carhibou-agent", MODE="0660"
ACTION=="add|change", SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="1e0e", TEST=="power/control", ATTR{power/control}="on"
`
}

func installSIMComUdevRule(operations udevOperations, path string) error {
	if err := operations.writeFile(path, []byte(simcomUdevRule()), 0o644); err != nil {
		return fmt.Errorf("install SIMCom udev rule: %w", err)
	}
	if err := operations.chmod(path, 0o644); err != nil {
		return fmt.Errorf("set SIMCom udev rule permissions: %w", err)
	}
	return reloadSIMComUdevRules(operations)
}

func uninstallSIMComUdevRule(operations udevOperations, path string) error {
	if err := operations.remove(path); err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return fmt.Errorf("remove SIMCom udev rule: %w", err)
	}
	return reloadSIMComUdevRules(operations)
}

func reloadSIMComUdevRules(operations udevOperations) error {
	for _, command := range [][]string{
		{"udevadm", "control", "--reload-rules"},
		{"udevadm", "trigger", "--settle", "--subsystem-match=usb", "--attr-match=idVendor=1e0e", "--action=change"},
	} {
		output, err := operations.run(command[0], command[1:]...)
		if err != nil {
			return fmt.Errorf("refresh SIMCom udev devices: %s: %w", strings.TrimSpace(string(output)), err)
		}
	}
	return nil
}

func ignoreCommand(name string, args ...string) { _ = exec.Command(name, args...).Run() }
