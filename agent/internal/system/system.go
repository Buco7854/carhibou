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
	ServiceName = "carhibou-agent.service"
	BinaryPath  = "/usr/local/bin/carhibou-agent"
	ConfigDir   = "/etc/carhibou-agent"
	DataDir     = "/var/lib/carhibou-agent"
)

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

func ignoreCommand(name string, args ...string) { _ = exec.Command(name, args...).Run() }
