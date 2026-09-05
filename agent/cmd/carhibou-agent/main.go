package main

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"net"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"reflect"
	"runtime"
	"slices"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/capture"
	"github.com/Buco7854/carhibou/agent/internal/client"
	"github.com/Buco7854/carhibou/agent/internal/model"
	"github.com/Buco7854/carhibou/agent/internal/profile"
	"github.com/Buco7854/carhibou/agent/internal/providers"
	agentruntime "github.com/Buco7854/carhibou/agent/internal/runtime"
	"github.com/Buco7854/carhibou/agent/internal/store"
	agentsystem "github.com/Buco7854/carhibou/agent/internal/system"
	"github.com/Buco7854/carhibou/agent/internal/usbrecovery"
)

var (
	version     = "dev"
	buildTarget = "dev"
)

const (
	// loopWatchdogLimit must expire before systemd's 90-second watchdog so the
	// goroutine stacks reach the journal. The loop runs every 250 ms regardless
	// of the vehicle sampling cadence.
	loopWatchdogLimit     = 60 * time.Second
	systemdNotifyInterval = 30 * time.Second
)

type paths struct{ config, data string }

func main() {
	if err := execute(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, "Error:", err)
		os.Exit(1)
	}
}

func execute(arguments []string) error {
	locations, remaining, err := globalArguments(arguments)
	if err != nil {
		return err
	}
	if len(remaining) == 0 {
		usage()
		return fmt.Errorf("a command is required")
	}
	command, arguments := remaining[0], remaining[1:]
	switch command {
	case "version", "--version":
		fmt.Printf("Carhibou agent %s (%s)\n", version, buildTarget)
		return nil
	case providers.ProbeChildCommand:
		if len(arguments) != 1 {
			return fmt.Errorf("%s requires one device path", providers.ProbeChildCommand)
		}
		return providers.RunProbeChild(arguments[0], os.Stdout)
	case "install":
		return commandInstall(locations, arguments)
	case "update":
		return commandUpdate(locations, arguments)
	case "uninstall":
		return commandUninstall(arguments)
	case "run":
		return commandRun(locations, arguments)
	case "status":
		return commandStatus(locations)
	case "doctor":
		return commandDoctor(locations, len(arguments) > 0 && arguments[0] == "--probe")
	case "logs":
		return runAttached("journalctl", "-u", agentsystem.ServiceName, "-n", "200", "--no-pager")
	case "config":
		return commandConfig(locations, arguments)
	case "devices":
		return commandDevices(locations, arguments)
	case "gps-info":
		return commandGPS(locations, arguments)
	case "obd-info":
		return commandOBD(locations, arguments)
	case "obd-selftest":
		return commandOBDSelfTest(locations, arguments)
	case "monitor":
		return commandMonitor(locations, arguments)
	case "can-record":
		return commandRecord(locations, arguments)
	case "replay-can":
		return commandReplay(arguments)
	case "help", "--help", "-h":
		usage()
		return nil
	default:
		usage()
		return fmt.Errorf("unknown command %q", command)
	}
}

func globalArguments(arguments []string) (paths, []string, error) {
	locations := paths{config: agentsystem.ConfigDir, data: agentsystem.DataDir}
	for len(arguments) > 0 {
		switch arguments[0] {
		case "--force":
			forceHardware = true
			arguments = arguments[1:]
		case "--config-dir", "--data-dir":
			if len(arguments) < 2 {
				return locations, nil, fmt.Errorf("%s requires a value", arguments[0])
			}
			if arguments[0] == "--config-dir" {
				locations.config = arguments[1]
			} else {
				locations.data = arguments[1]
			}
			arguments = arguments[2:]
		default:
			return locations, arguments, nil
		}
	}
	return locations, arguments, nil
}

func usage() {
	fmt.Print(`Usage: carhibou-agent [--config-dir PATH] [--data-dir PATH] [--force] COMMAND

Commands:
  install       Enroll this host and install its systemd service
  update        Download and verify another agent version
  uninstall     Remove the service, credentials, configuration, and queue
  run           Run the telemetry service
  status        Show credentials and queued telemetry
  doctor        Show installation diagnostics; --probe identifies each serial port
  logs          Show recent service logs
  config        Print the accepted configuration; --pull fetches it from the server now
  devices       Show device choices; use "devices set" to change them
  gps-info      Enable the receiver and print position fixes
  obd-info      Read adapter, request, and CAN traffic diagnostics
  obd-selftest  Exercise and report the exact profile monitoring pipeline
  monitor       Print live position and vehicle metrics together
  can-record    Record CAN frames to a portable JSONL capture
  replay-can    Replay a capture, optionally through a profile
  version       Print build version and target

--force lets a hardware command run while the service holds the ports. The reading
cannot be trusted when it does, because both processes read the same stream.
`)
}

func commandInstall(locations paths, arguments []string) error {
	flags := flag.NewFlagSet("install", flag.ContinueOnError)
	server := flags.String("server", "", "Carhibou server origin")
	token := flags.String("token", "", "one-time enrollment token")
	allowHTTP := flags.Bool("allow-insecure-http", false, "allow clear-text HTTP")
	updateOnly := flags.Bool("update-only", false, "refresh service without enrollment")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	if *server == "" {
		return fmt.Errorf("--server is required")
	}
	if !*updateOnly && *token == "" {
		return fmt.Errorf("--token is required for initial enrollment")
	}
	if err := agentsystem.SetupIdentityAndDirectories(); err != nil {
		return err
	}
	if !*updateOnly {
		hostname, _ := os.Hostname()
		modelName := strings.TrimSpace(strings.TrimRight(string(readOptional("/proc/device-tree/model")), "\x00"))
		response, err := client.Enroll(*server, *token, hostname, version, map[string]any{
			"os": runtime.GOOS, "architecture": runtime.GOARCH, "target": buildTarget, "model": modelName,
		}, *allowHTTP)
		if err != nil {
			return err
		}
		normalized, _ := client.NormalizeServerURL(*server, *allowHTTP)
		credentials := store.Credentials{ServerURL: normalized, AgentID: response.AgentID, VehicleID: response.VehicleID, Credential: response.Credential, AllowInsecureHTTP: *allowHTTP}
		credentialsPath := filepath.Join(locations.config, "credentials.json")
		configPath := filepath.Join(locations.config, "config.json")
		if err := store.WriteJSONAtomic(credentialsPath, credentials, 0o600); err != nil {
			return err
		}
		if _, err := (store.ConfigurationStore{Path: configPath}).InstallIfNewer(response.Config); err != nil {
			return err
		}
		if err := agentsystem.ChownAgent(credentialsPath); err != nil {
			return err
		}
		if err := agentsystem.ChownAgent(configPath); err != nil {
			return err
		}
		fmt.Printf("Enrolled agent %s\n", response.AgentID)
	}
	// Before the service starts, so the ports are still free to resolve and the
	// rights are in place the first time a recovery ladder needs them.
	grantUSBRecoveryRights(configuredSerialPaths(locations))
	if err := agentsystem.InstallService(); err != nil {
		return err
	}
	fmt.Printf("Carhibou agent %s installed. Run: sudo carhibou-agent doctor\n", version)
	return nil
}

func commandUpdate(locations paths, arguments []string) error {
	flags := flag.NewFlagSet("update", flag.ContinueOnError)
	requested := flags.String("version", "", "version to install")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	if *requested == "" {
		return fmt.Errorf("--version is required")
	}
	credentials, err := loadCredentials(locations)
	if err != nil {
		return err
	}
	api, err := client.New(credentials.ServerURL, credentials.Credential, version, credentials.AllowInsecureHTTP)
	if err != nil {
		return err
	}
	target, err := agentsystem.DetectTarget(buildTarget)
	if err != nil {
		return err
	}
	// An upgrade is where a rule written for hardware that has since been
	// replaced gets corrected, so the rights are refreshed before the restart.
	grantUSBRecoveryRights(configuredSerialPaths(locations))
	if err := agentsystem.Update(api, *requested, target); err != nil {
		return err
	}
	fmt.Printf("Carhibou agent updated to %s\n", *requested)
	return nil
}

func commandUninstall(arguments []string) error {
	flags := flag.NewFlagSet("uninstall", flag.ContinueOnError)
	yes := flags.Bool("yes", false, "skip confirmation")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	return agentsystem.Uninstall(*yes)
}

func commandStatus(locations paths) error {
	credentials := filepath.Join(locations.config, "credentials.json")
	queue, err := store.OpenQueue(filepath.Join(locations.data, "queue.sqlite3"))
	if err != nil {
		return err
	}
	defer queue.Close()
	depth, err := queue.Depth()
	if err != nil {
		return err
	}
	installed := fileExists(credentials)
	fmt.Printf("Carhibou agent %s\nCredentials: %s\nQueued telemetry: %d\n", version, map[bool]string{true: "installed", false: "missing"}[installed], depth)
	if !installed {
		return fmt.Errorf("credentials are missing")
	}
	return nil
}

func commandDoctor(locations paths, probe bool) error {
	hardware, hardwareErr := (store.HardwareStore{Path: filepath.Join(locations.config, "hardware.json")}).Load()
	result := map[string]any{
		"version": version, "target": buildTarget, "credentials": fileExists(filepath.Join(locations.config, "credentials.json")),
		"queue_directory_writable": directoryWritable(locations.data), "serial_candidates": store.SerialCandidates(),
	}
	if hardwareErr != nil {
		result["hardware_error"] = hardwareErr.Error()
	} else {
		result["hardware_selection"] = hardware
		if probe {
			if err := requireExclusiveHardware(); err != nil {
				return err
			}
			// Opening every port is the only way to tell identical USB names apart.
			// The service must be stopped first, or it still holds them.
			devices := resolveDevices(hardware, locations, true)
			result["ports"] = devices.reports
			result["gps_device"] = nullIfEmpty(devices.gps)
			result["obd_device"] = nullIfEmpty(devices.obd)
			result["modem_device"] = nullIfEmpty(devices.modem)
		} else if detection, found := detectionStore(locations).Load(); found {
			result["detected_by_service"] = detection
		}
	}
	printJSON(result)
	if hardwareErr != nil || result["credentials"] != true || result["queue_directory_writable"] != true {
		return fmt.Errorf("one or more diagnostic checks failed")
	}
	return nil
}

func commandDevices(locations paths, arguments []string) error {
	hardwareStore := store.HardwareStore{Path: filepath.Join(locations.config, "hardware.json")}
	hardware, err := hardwareStore.Load()
	if err != nil {
		return err
	}
	if len(arguments) > 0 && arguments[0] == "set" {
		flags := flag.NewFlagSet("devices set", flag.ContinueOnError)
		gps := flags.String("gps", "", "auto, off, or /dev path")
		obd := flags.String("obd", "", "auto, off, or /dev path")
		modem := flags.String("modem", "", "off or /dev path of the cellular control port")
		if err := flags.Parse(arguments[1:]); err != nil {
			return err
		}
		if *gps == "" && *obd == "" && *modem == "" {
			return fmt.Errorf("choose --gps, --obd and/or --modem")
		}
		if *gps != "" {
			hardware.GPS = *gps
		}
		if *obd != "" {
			hardware.OBD = *obd
		}
		if *modem != "" {
			hardware.Modem = *modem
		}
		if err := hardware.Validate(); err != nil {
			return err
		}
		for source, value := range map[string]string{"GPS": hardware.GPS, "OBD": hardware.OBD, "Modem": hardware.Modem} {
			if value != "" && value != store.Auto && value != store.Off && !fileExists(value) {
				return fmt.Errorf("%s device does not exist: %s", source, value)
			}
		}
		if err := hardwareStore.Save(hardware); err != nil {
			return err
		}
		// The saved choice is what the rights follow, so a new adapter or modem
		// is granted its own reset access here rather than at the next upgrade.
		grantUSBRecoveryRights(configuredSerialPaths(locations))
		printJSON(hardware)
		fmt.Println("Saved. Restart with: sudo systemctl restart carhibou-agent")
		return nil
	}
	if len(arguments) > 0 {
		return fmt.Errorf("unknown devices action %q", arguments[0])
	}
	// Listing alone stays cheap and does not open hardware, so it is safe while the
	// service is running. "doctor --probe" identifies ports, once the service is stopped.
	listing := map[string]any{"selection": hardware, "serial_candidates": store.SerialCandidates()}
	if detection, found := detectionStore(locations).Load(); found {
		listing["detected_by_service"] = detection
	}
	printJSON(listing)
	return nil
}

func commandGPS(locations paths, arguments []string) error {
	if err := requireExclusiveHardware(); err != nil {
		return err
	}
	flags := flag.NewFlagSet("gps-info", flag.ContinueOnError)
	device := flags.String("device", "", "serial device")
	seconds := flags.Int("seconds", 10, "read duration in seconds")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	if *seconds <= 0 {
		return fmt.Errorf("--seconds must be greater than zero")
	}
	hardware, err := loadHardware(locations)
	if err != nil {
		return err
	}
	// A position diagnostic needs the device that was proven by the running
	// service, not another broad sweep across a five-interface modem. A fresh
	// sweep remains available through doctor --probe when the hardware actually
	// changed; using the cache here also lets a quiet receiver be relit through
	// its known control port.
	devices := resolveDevices(hardware, locations, false)
	if *device != "" {
		devices.gps = *device
		report := providers.ProbeDevice(*device)
		devices.gpsStreams = report.NMEA
		if report.Role == providers.RoleModem {
			devices.modem = *device
		}
	}
	var position agentruntime.PositionProvider
	closePosition := func() {}
	if devices.gps == "" {
		fmt.Fprintln(os.Stderr, "No responsive GPS role was found; starting automatic recovery")
		recovery := newPositionRecovery(hardware, locations, devices, 1, newSerialOwnership())
		// resolveDevices already performed or reused the ordinary discovery
		// attempt above. A diagnostic is interactive, so it can move directly to
		// the bounded recovery attempt instead of asking the user to run another
		// command and remember a port number.
		recovery.missingAttempts = 1
		position, err = recovery.acquire()
		devices = recovery.devices
		if err != nil {
			return fmt.Errorf("automatic GPS recovery failed: %w", err)
		}
		if closer, ok := position.(interface{ Close() }); ok {
			closePosition = closer.Close
		}
	} else {
		position, closePosition, err = startPosition(devices, 1)
		if err != nil {
			return err
		}
	}
	fmt.Fprintf(os.Stderr, "Reading %s for %ds\n", devices.gps, *seconds)
	seen, traffic, readErr := readPositionDiagnostic(position, time.Duration(*seconds)*time.Second)
	closePosition()
	if !seen {
		if traffic {
			// Valid sentences without a valid position prove the serial path and
			// receiver are healthy. Resetting cannot give an indoor antenna a view
			// of the sky.
			return fmt.Errorf("no fix from %s: the receiver is streaming but has no satellite position, which usually means the antenna needs a clear view of the sky", devices.gps)
		}

		fmt.Fprintln(os.Stderr, "The known receiver produced no NMEA traffic; starting automatic recovery")
		recovery := newPositionRecovery(hardware, locations, devices, 1, newSerialOwnership())
		recovery.attempted = true
		recovered, recoveryErr := recovery.acquire()
		if recoveryErr != nil {
			if readErr != nil {
				return fmt.Errorf("GPS read failed (%v), then automatic recovery failed: %w", readErr, recoveryErr)
			}
			return fmt.Errorf("no NMEA traffic from %s, and automatic recovery failed: %w", devices.gps, recoveryErr)
		}
		if closer, ok := recovered.(interface{ Close() }); ok {
			defer closer.Close()
		}
		fmt.Fprintf(os.Stderr, "Recovery completed; reading for another %ds\n", *seconds)
		seen, traffic, readErr = readPositionDiagnostic(recovered, time.Duration(*seconds)*time.Second)
		if !seen {
			if traffic {
				return fmt.Errorf("receiver recovered and is streaming, but has no satellite position; give the antenna a clear view of the sky")
			}
			if readErr != nil {
				return fmt.Errorf("receiver still produced no NMEA traffic after automatic recovery: %w", readErr)
			}
			return fmt.Errorf("receiver still produced no NMEA traffic after automatic recovery")
		}
	}
	return nil
}

func readPositionDiagnostic(position agentruntime.PositionProvider, duration time.Duration) (bool, bool, error) {
	deadline := time.Now().Add(duration)
	seen := false
	var lastErr error
	for time.Now().Before(deadline) {
		fix, err := position.Read()
		if err != nil {
			lastErr = err
		}
		if fix != nil {
			seen = true
			printJSON(fix)
		}
		time.Sleep(time.Second)
	}
	traffic := seen
	if stream, ok := position.(*providers.NMEAProvider); ok {
		traffic = stream.HasTraffic()
	}
	return seen, traffic, lastErr
}

func commandOBD(locations paths, arguments []string) error {
	if err := requireExclusiveHardware(); err != nil {
		return err
	}
	flags := flag.NewFlagSet("obd-info", flag.ContinueOnError)
	device := flags.String("device", "", "serial device")
	seconds := flags.Int("seconds", defaultCANSurveySeconds, "CAN listen duration in seconds")
	watch := flags.String("watch", "", "monitor one hexadecimal CAN identifier")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	if *seconds <= 0 {
		return fmt.Errorf("--seconds must be greater than zero")
	}
	if flags.NArg() != 0 {
		return fmt.Errorf("obd-info accepts flags only")
	}
	watchID, err := parseOptionalCANID(*watch)
	if err != nil {
		return err
	}
	if *device == "" {
		hardware, err := loadHardware(locations)
		if err != nil {
			return err
		}
		*device = resolveDevices(hardware, locations, true).obd
	}
	if *device == "" {
		return fmt.Errorf("no OBD adapter found; run 'carhibou-agent doctor --probe'")
	}
	fmt.Fprintln(os.Stderr, "Connecting to", *device)
	adapter := providers.NewOBDAdapter(*device)
	if err := adapter.Connect(); err != nil {
		return err
	}
	defer adapter.Close()
	identity, err := adapter.Identity()
	if err != nil {
		return err
	}
	result := map[string]any{
		"device": *device, "adapter": identity["adapter"], "firmware": identity["firmware"],
		"uart_baud_rate": adapter.BaudRate(),
	}
	// The adapter answers whether or not a vehicle is listening, so what it says
	// about itself is reported separately from what the vehicle said. Voltage in
	// particular comes from the connector and works with the ignition off.
	if voltage, err := adapter.Voltage(); err == nil {
		result["supply_voltage"] = voltage
	}
	if protocol, err := adapter.Protocol(); err == nil {
		result["protocol"] = protocol
	}

	answered := false
	if lines, err := adapter.Command("0902", 0); err == nil {
		result["vin"] = nullIfEmpty(providers.ParseVIN(lines))
		if providers.VehicleAnswered(lines) {
			answered = true
		} else {
			result["vehicle_reply"] = lines
		}
	}
	result["dtcs"] = []string{}
	if lines, err := adapter.Command("03", 0); err == nil {
		result["dtcs"] = providers.ParseDTC(lines)
		if providers.VehicleAnswered(lines) {
			answered = true
		}
	}
	result["answers_requests"] = answered

	// Requests and broadcasts are separate questions, and for a profile only the
	// second one matters. Plenty of vehicles answer no standard diagnostic request
	// at all while broadcasting everything a profile decodes, so asking 0902 and
	// stopping there measured the wrong thing and then explained it wrongly.
	duration := time.Duration(*seconds) * time.Second
	if watchID != nil {
		if err := adapter.WatchCANID(*watchID); err != nil {
			return err
		}
		result["watch_id"] = formatCANID(*watchID)
		fmt.Fprintf(os.Stderr, "Watching CAN identifier %s for %s\n", formatCANID(*watchID), duration)
	} else {
		fmt.Fprintf(os.Stderr, "Listening for CAN frames for %s\n", duration)
	}
	seen := map[int]int{}
	frames := 0
	started := time.Now()
	var monitorReport providers.MonitorReport
	if watchID != nil {
		monitorReport, err = adapter.MonitorReport(duration, func(frame model.CANFrame) {
			frames++
			seen[frame.CANID]++
		})
	} else {
		monitorReport, err = adapter.MonitorAllReport(duration, func(frame model.CANFrame) {
			frames++
			seen[frame.CANID]++
		})
	}
	elapsed := time.Since(started).Seconds()
	if err != nil {
		result["can_error"] = err.Error()
	}
	result["can_frames"] = frames
	result["can_duration_seconds"] = elapsed
	result["can_frame_rate_hz"] = float64(frames) / elapsed
	result["can_id_counts"] = canIDCounts(seen)
	result["can_ids"] = sortedCANIDs(seen)
	result["can_capture"] = monitorReport
	printJSON(result)
	explainOBD(result, answered, frames, monitorReport)
	return nil
}

func commandOBDSelfTest(locations paths, arguments []string) error {
	if err := requireExclusiveHardware(); err != nil {
		return err
	}
	flags := flag.NewFlagSet("obd-selftest", flag.ContinueOnError)
	device := flags.String("device", "", "serial device")
	seconds := flags.Int("seconds", defaultCANSurveySeconds, "diagnostic survey window in seconds; differs from the deployed service burst")
	deadlineSeconds := flags.Int("deadline-seconds", 0, "overall limit in seconds; 0 derives one from --seconds")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	if *seconds <= 0 {
		return fmt.Errorf("--seconds must be greater than zero")
	}
	if *deadlineSeconds < 0 {
		return fmt.Errorf("--deadline-seconds cannot be negative")
	}
	if flags.NArg() != 0 {
		return fmt.Errorf("obd-selftest accepts flags only")
	}
	if *device == "" {
		hardware, err := loadHardware(locations)
		if err != nil {
			return err
		}
		*device = resolveDevices(hardware, locations, true).obd
	}
	if *device == "" {
		return fmt.Errorf("no OBD adapter found; run 'carhibou-agent doctor --probe'")
	}
	configuration, err := (store.ConfigurationStore{Path: filepath.Join(locations.config, "config.json")}).Load()
	if err != nil {
		return err
	}
	decoder, err := vehicleProfileDecoder(configuration)
	if err != nil {
		return err
	}
	if decoder == nil {
		return fmt.Errorf("obd-selftest requires an assigned CAN vehicle profile")
	}

	adapter := providers.NewOBDAdapter(*device)
	if err := adapter.Connect(); err != nil {
		return err
	}
	defer adapter.Close()
	window := time.Duration(*seconds) * time.Second
	serviceBurstWindow := providers.ProfileBurstWindow(
		time.Duration(configuration.Sampling.DefaultSeconds) * time.Second,
	)
	// Worst case is every protocol tried, a baud fallback that tries them all
	// again, then the filtered and unfiltered verifications.
	overall := time.Duration(*deadlineSeconds) * time.Second
	if overall == 0 {
		overall = window*time.Duration(2*providers.CANProtocolCount()+2) + 30*time.Second
	}
	started := time.Now()
	fmt.Fprintf(os.Stderr, "Self-test on %s, up to %s. Diagnostic survey stages listen for %s; this differs from the deployed service sample window of %s.\n",
		*device, overall.Round(time.Second), window, serviceBurstWindow)
	progress := func(stage string) {
		fmt.Fprintf(os.Stderr, "[%4.0fs] %s\n", time.Since(started).Seconds(), stage)
	}
	preparation, prepareErr := providers.PrepareProfileMonitor(
		adapter, decoder.CANIDs(), window, 10, true, func(model.CANFrame) {},
		progress, started.Add(overall),
	)
	result := map[string]any{
		"device":                    *device,
		"uart_baud_rate":            adapter.BaudRate(),
		"diagnostic_window_seconds": *seconds,
		"service_burst_window_ms":   serviceBurstWindow.Milliseconds(),
		"pipeline":                  preparation,
	}
	if identity, identityErr := adapter.Identity(); identityErr == nil {
		result["adapter"] = identity["adapter"]
		result["firmware"] = identity["firmware"]
	}
	result["elapsed_seconds"] = float64(int(time.Since(started).Seconds()*10)) / 10
	if prepareErr != nil {
		result["error"] = prepareErr.Error()
	} else {
		result["conclusion"] = profileSelfTestConclusion(preparation)
	}
	printJSON(result)
	if errors.Is(prepareErr, providers.ErrPreparationDeadline) {
		fmt.Fprintf(os.Stderr, "Stopped at the %s limit. The stages above are what completed.\n", overall.Round(time.Second))
		return prepareErr
	}
	if prepareErr != nil {
		return prepareErr
	}
	fmt.Fprintln(os.Stderr, profileSelfTestConclusion(preparation))
	return nil
}

func profileSelfTestConclusion(preparation providers.ProfileMonitorPreparation) string {
	// CAN auto formatting is disabled after the protocol is selected and the
	// filters are installed, because selecting a protocol can clear it. Nothing
	// but frames parsed after that order proves it on the car, so the count is
	// said out loud rather than left to be reconstructed from the stage traces.
	ordering := fmt.Sprintf(
		" %d frames parsed after CAN auto formatting was disabled, which follows protocol selection and filter installation.",
		preparation.FramesAfterRawCAN,
	)
	switch {
	case preparation.UseUnfiltered:
		return "Filtered STM parsed no frames while STMA did; the service will use unfiltered monitoring with software profile filtering." + ordering
	case preparation.HardwareFilterGood:
		return "Filtered STM parsed frames; the service will keep hardware-filtered monitoring." + ordering
	case preparation.Unfiltered != nil:
		return "Neither filtered STM nor STMA parsed a frame; verify the ignition state and inspect the raw and malformed-line counts above." + ordering
	default:
		return "The profile monitoring pipeline did not complete." + ordering
	}
}

const defaultCANSurveySeconds = 10

func parseOptionalCANID(value string) (*int, error) {
	value = strings.TrimSpace(value)
	if value == "" {
		return nil, nil
	}
	parsed, err := strconv.ParseUint(strings.TrimPrefix(strings.ToLower(value), "0x"), 16, 29)
	if err != nil || parsed > 0x1FFFFFFF {
		return nil, fmt.Errorf("--watch must be a hexadecimal CAN identifier between 0 and 1FFFFFFF")
	}
	canID := int(parsed)
	return &canID, nil
}

func formatCANID(canID int) string {
	if canID <= 0x7FF {
		return fmt.Sprintf("%03X", canID)
	}
	return fmt.Sprintf("%08X", canID)
}

func canIDCounts(seen map[int]int) map[string]int {
	counts := make(map[string]int, len(seen))
	for canID, count := range seen {
		counts[formatCANID(canID)] = count
	}
	return counts
}

func sortedCANIDs(seen map[int]int) []string {
	ids := make([]int, 0, len(seen))
	for canID := range seen {
		ids = append(ids, canID)
	}
	sort.Ints(ids)
	listed := make([]string, 0, len(ids))
	for _, canID := range ids {
		listed = append(listed, formatCANID(canID))
	}
	return listed
}

func explainOBD(result map[string]any, answered bool, frames int, report providers.MonitorReport) {
	if report.DroppedData {
		fmt.Fprintln(os.Stderr, "The adapter reported dropped or malformed CAN data; counts are incomplete.")
	}
	if report.DataErrors > 0 {
		fmt.Fprintf(os.Stderr, "The adapter marked %d CAN frames with receive-validation errors; valid payload prefixes were retained.\n", report.DataErrors)
	}
	if frames > 0 {
		if !answered {
			fmt.Fprintln(os.Stderr, "The vehicle answers no standard diagnostic request, which is normal on many")
			fmt.Fprintln(os.Stderr, "electric vehicles, but it is broadcasting. A profile reads those broadcasts,")
			fmt.Fprintln(os.Stderr, "so the identifiers listed above are what it has to work with.")
		}
		return
	}
	// No broadcasts at all. The adapter's own supply says whether that is a
	// sleeping vehicle or a live one that is not talking on this protocol.
	if watchID, ok := result["watch_id"].(string); ok {
		fmt.Fprintf(os.Stderr, "No frames arrived for CAN identifier %s.\n", watchID)
		return
	}
	voltage, _ := result["supply_voltage"].(string)
	awake := false
	if trimmed := strings.TrimSuffix(strings.TrimSpace(voltage), "V"); trimmed != "" {
		if value, err := strconv.ParseFloat(trimmed, 64); err == nil && value >= 13.0 {
			awake = true
		}
	}
	fmt.Fprintln(os.Stderr, "No CAN frames arrived.")
	if awake {
		fmt.Fprintf(os.Stderr, "The supply reads %s, so the vehicle is awake and something is charging its\n", voltage)
		fmt.Fprintln(os.Stderr, "battery. Nothing is being broadcast on this protocol: the adapter may have")
		fmt.Fprintln(os.Stderr, "settled on the wrong one, or this bus may not be wired to the diagnostic port.")
		return
	}
	fmt.Fprintln(os.Stderr, "The supply suggests a resting battery, so the vehicle is most likely asleep.")
	fmt.Fprintln(os.Stderr, "Switch the ignition on and run this again.")
}

// commandMonitor prints what the agent would sample, once per interval, so a
// wiring or antenna problem is visible without waiting for a dashboard round trip.
func commandMonitor(locations paths, arguments []string) error {
	if err := requireExclusiveHardware(); err != nil {
		return err
	}
	flags := flag.NewFlagSet("monitor", flag.ContinueOnError)
	seconds := flags.Int("interval", 2, "seconds between reads")
	count := flags.Int("count", 0, "number of reads, or zero to run until interrupted")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	if *seconds <= 0 {
		return fmt.Errorf("--interval must be greater than zero")
	}
	hardware, err := loadHardware(locations)
	if err != nil {
		return err
	}
	devices := resolveDevices(hardware, locations, true)
	fmt.Fprintf(os.Stderr, "GPS %s | OBD %s\n", orNone(devices.gps), orNone(devices.obd))
	configuration, err := (store.ConfigurationStore{Path: filepath.Join(locations.config, "config.json")}).Load()
	if err != nil {
		return err
	}
	position, closePosition, err := startPosition(devices, configuration.Sampling.Longest())
	if err != nil {
		return err
	}
	defer closePosition()
	vehicle, err := vehicleProvider(devices.obd, configuration, cooledDownOBDResetter(resetOBDDevice, time.Now))
	if err != nil {
		return err
	}
	defer vehicle.Close()
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	for reads := 0; *count == 0 || reads < *count; reads++ {
		select {
		case <-ctx.Done():
			return nil
		default:
		}
		row := map[string]any{"at": time.Now().UTC().Format(time.RFC3339)}
		fix, fixErr := position.Read()
		switch {
		case fixErr != nil:
			row["gps_error"] = fixErr.Error()
		case fix == nil:
			row["gps"] = "no fix"
		default:
			row["gps"] = fix
		}
		observations, metricsErr := vehicle.ReadObservations()
		if metricsErr != nil {
			row["obd_error"] = metricsErr.Error()
		} else {
			values := map[string]any{}
			for _, observation := range observations.List() {
				values[observation.Key] = observation.Value
			}
			row["metrics"] = values
		}
		printJSON(row)
		time.Sleep(time.Duration(*seconds) * time.Second)
	}
	return nil
}

func orNone(value string) string {
	if value == "" {
		return "none"
	}
	return value
}

func commandRecord(locations paths, arguments []string) error {
	flags := flag.NewFlagSet("can-record", flag.ContinueOnError)
	device := flags.String("device", "", "serial device")
	profileID := flags.String("profile", "", "profile id")
	seconds := flags.Int("seconds", 30, "record duration in seconds")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	if *seconds <= 0 {
		return fmt.Errorf("--seconds must be greater than zero")
	}
	if flags.NArg() != 1 {
		return fmt.Errorf("capture output path is required")
	}
	if *device == "" {
		hardware, err := loadHardware(locations)
		if err != nil {
			return err
		}
		*device = resolveDevices(hardware, locations, true).obd
	}
	if *device == "" {
		return fmt.Errorf("no OBD adapter found; run 'carhibou-agent doctor --probe'")
	}
	adapter := providers.NewOBDAdapter(*device)
	if err := adapter.Connect(); err != nil {
		return err
	}
	defer adapter.Close()
	if err := adapter.SelectProtocol("6"); err != nil {
		return err
	}
	output, err := os.Create(flags.Arg(0))
	if err != nil {
		return err
	}
	defer output.Close()
	recorder, err := capture.NewRecorder(output, map[string]any{"adapter": *device, "vehicle_profile": *profileID})
	if err != nil {
		return err
	}
	if err := adapter.Monitor(time.Duration(*seconds)*time.Second, func(frame model.CANFrame) {
		if err := recorder.Write(frame); err != nil {
			fmt.Fprintln(os.Stderr, "capture write failed:", err)
		}
	}); err != nil {
		return err
	}
	fmt.Printf("Capture written to %s\n", flags.Arg(0))
	return nil
}

func commandReplay(arguments []string) error {
	flags := flag.NewFlagSet("replay-can", flag.ContinueOnError)
	profilePath := flags.String("profile", "", "YAML or JSON profile")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	if flags.NArg() != 1 {
		return fmt.Errorf("capture path is required")
	}
	recording, err := capture.Read(flags.Arg(0))
	if err != nil {
		return err
	}
	var decoder *profile.DecoderEngine
	if *profilePath != "" {
		decoder, err = profile.FromFile(*profilePath)
		if err != nil {
			return err
		}
	}
	metrics := map[string]any{}
	for _, frame := range recording.Frames {
		row := map[string]any{"type": "frame", "timestamp": frame.Timestamp, "can_id": fmt.Sprintf("0x%03X", frame.CANID), "data": strings.ToUpper(hex.EncodeToString(frame.Data)), "metadata": recording.Metadata}
		if decoder != nil {
			decoded := decoder.Decode(frame, metrics)
			row["signals"] = decoded
			for _, signal := range decoded {
				metrics[signal.Name] = signal.Value
			}
		}
		printJSON(row)
	}
	fmt.Fprintf(os.Stderr, "Replayed %d frames\n", len(recording.Frames))
	return nil
}

// resolvedDevices is which serial path ended up serving which role.
type resolvedDevices struct {
	gps   string
	obd   string
	modem string
	// gpsStreams distinguishes a path that publishes sentences by itself from one
	// that only answers a position when polled over AT. The same path can be the
	// modem control port as well, which is the usual arrangement.
	gpsStreams bool
	reports    []providers.PortReport
}

// resolveDevices decides the role of each serial path.
//
// An explicit selection is honoured without opening anything. Only "auto" probes,
// because the USB product name cannot distinguish the five identical interfaces a
// cellular module publishes, and picking the wrong one leaves the agent silently
// without a position.
// serialCandidates, sweepPorts and probeKnownPort are the three host operations
// discovery performs. Tests replace them with a fake port set, which is how the
// two acquirers can be run against each other without serial hardware.
var (
	serialCandidates     = store.SerialCandidates
	sweepPorts           = providers.ProbeAll
	probeKnownPort       = providers.ProbeKnownDevice
	buildVehicleProvider = vehicleProvider
)

func detectionStore(locations paths) store.DetectionStore {
	return store.DetectionStore{Path: filepath.Join(locations.data, "detection.json")}
}

// resolveDevices decides the role of each serial path, reusing the stored answer
// unless asked for a fresh one.
//
// A sweep is seconds per port and nearly all of it is spent waiting, so repeating
// it on every service restart is a slow start for nothing. The stored answer is
// used while the ports it was made against are still the ports that are there.
// Diagnostics always ask for a fresh one: they are run precisely when something
// has changed or broken, which is when a remembered answer is worth least.
// serialSweep serialises port enumeration. The vehicle and position sources both
// reacquire in the background now, and two sweeps at once would open the same
// ports from two goroutines and split every reply between them.
var serialSweep sync.Mutex

// Roles naming the two acquirers in the ownership registry below.
const (
	vehicleRole  = "vehicle"
	positionRole = "position"
)

// serialOwnership records the ports each acquirer is using, so neither probes
// hardware the other holds.
//
// The mutex above stops two sweeps overlapping, but a sweep still opened and
// wrote to every candidate, and the exclusions were name-based snapshots taken
// once at startup: the vehicle sweep skipped the GPS path the service resolved
// when it began, not the one the position source had since moved to, and the
// position sweep skipped the OBD path only when one had already been detected.
// Either way the port that was actually in use could be opened by the other
// side, which reports it busy and fails an acquisition that had nothing wrong
// with it. A role declares its ports before it opens them and re-declares on
// every attempt, so a source that moves stops protecting the port it left.
type serialOwnership struct {
	mutex sync.Mutex
	held  map[string][]string
}

func newSerialOwnership() *serialOwnership {
	return &serialOwnership{held: map[string][]string{}}
}

// claim and heldByOthers tolerate a nil registry, which is what a diagnostic
// command running with the service stopped has: nobody else holds anything.
func (ownership *serialOwnership) claim(role string, paths ...string) {
	if ownership == nil {
		return
	}
	ownership.mutex.Lock()
	defer ownership.mutex.Unlock()
	ownership.held[role] = compactStrings(paths)
}

// heldByOthers lists the ports every role but this one is using.
func (ownership *serialOwnership) heldByOthers(role string) []string {
	if ownership == nil {
		return nil
	}

	ownership.mutex.Lock()
	defer ownership.mutex.Unlock()
	paths := []string{}
	for owner, owned := range ownership.held {
		if owner != role {
			paths = append(paths, owned...)
		}
	}
	sort.Strings(paths)
	return paths
}

// withoutOwnedPorts drops the candidates another role is holding. Comparison
// goes through the same symlink resolution the distinct-device check uses,
// because a /dev/serial/by-id name and a /dev/ttyUSB number are one device.
// sweepUnownedPorts probes candidates, re-asking before each one whether the
// other source has claimed it in the meantime.
//
// A list filtered once at the start goes stale while the sweep runs: a probe
// holds each port for seconds, so a source that resolves its device a moment
// after the sweep began would still have that port opened underneath it. The
// skip is announced, because a port that was never examined is not the same as
// one that answered nothing.
func sweepUnownedPorts(
	role string, candidates []string, ownership *serialOwnership, announce func(providers.PortReport),
) []providers.PortReport {
	reports := make([]providers.PortReport, 0, len(candidates))
	for _, candidate := range candidates {
		if len(withoutOwnedPorts([]string{candidate}, ownership.heldByOthers(role))) == 0 {
			fmt.Fprintf(os.Stderr, "%s probe %s skipped: the other source is using it\n", role, candidate)
			continue
		}
		reports = append(reports, sweepPorts([]string{candidate}, announce)...)
	}
	return reports
}

func withoutOwnedPorts(candidates, owned []string) []string {
	if len(owned) == 0 {
		return candidates
	}
	kept := make([]string, 0, len(candidates))
	for _, candidate := range candidates {
		if slices.ContainsFunc(owned, func(path string) bool {
			return agentruntime.ValidateDistinctDevices(path, candidate) != nil
		}) {
			continue
		}
		kept = append(kept, candidate)
	}
	return kept
}

func resolveDevices(hardware store.Hardware, locations paths, refresh bool) resolvedDevices {
	serialSweep.Lock()
	defer serialSweep.Unlock()
	result := resolvedDevices{gps: hardware.GPS, obd: hardware.OBD, modem: hardware.Modem}
	if hardware.GPS == store.Auto || hardware.OBD == store.Auto {
		candidates := serialCandidates()
		cache := detectionStore(locations)
		previous, previousFound := cache.Load()
		if !refresh {
			if previousFound && previous.Usable(candidates) {
				return fromDetection(hardware, previous)
			}
		}
		// A sweep takes a couple of seconds per port. Reporting each one as it
		// finishes is what separates "still working" from "hung", both for an
		// operator running a diagnostic and in the service journal.
		result.reports = sweepPorts(candidates, func(report providers.PortReport) {
			fmt.Fprintf(os.Stderr, "probe %s -> %s\n", report.Device, describePort(report))
		})
		defer func() {
			detection := store.Detection{
				At:         time.Now().UTC().Format(time.RFC3339),
				GPS:        result.gps,
				OBD:        result.obd,
				Modem:      result.modem,
				GPSStreams: result.gpsStreams,
				Candidates: candidates,
				Ports:      result.reports,
			}
			// A failed diagnostic sweep is evidence about this attempt, not
			// evidence that the roles which worked before ceased to exist. Keep
			// last-known roles while the same paths are still enumerated, so one
			// transiently mute SIM7600 cannot erase the route used to recover it.
			if previousFound && previous.Usable(candidates) {
				if detection.GPS == "" {
					detection.GPS = previous.GPS
					detection.GPSStreams = previous.GPSStreams
				}
				if detection.OBD == "" {
					detection.OBD = previous.OBD
				}
				if detection.Modem == "" {
					detection.Modem = previous.Modem
				}
			}
			if err := cache.Save(detection); err != nil {
				fmt.Fprintln(os.Stderr, "Could not record hardware detection:", err)
			}
		}()
		probedGPS, probedOBD, probedModem := providers.SelectRoles(result.reports)
		if result.modem == "" {
			result.modem = probedModem
		}
		if hardware.GPS == store.Auto {
			result.gps = probedGPS
		}
		if hardware.OBD == store.Auto {
			result.obd = probedOBD
		}
	}
	if result.gps == store.Off || result.gps == store.Auto {
		result.gps = ""
	}
	if result.obd == store.Off || result.obd == store.Auto {
		result.obd = ""
	}
	if result.modem == store.Off {
		result.modem = ""
	}
	if result.gps != "" && result.modem == "" {
		result.modem = modemPath(result.reports, result.gps)
	}
	result.gpsStreams = providers.StreamsNMEA(result.reports, result.gps)
	return result
}

// resolvePositionDevices refreshes only the position-side roles while the
// service may be continuously monitoring the OBD adapter. A general discovery
// sweep is safe at startup, before providers own ports; a recovery sweep is not:
// opening the live ELM/STN path and sending ATI would interrupt its CAN monitor.
func resolvePositionDevices(
	hardware store.Hardware, locations paths, known resolvedDevices, ownership *serialOwnership,
) resolvedDevices {
	serialSweep.Lock()
	defer serialSweep.Unlock()

	allCandidates := serialCandidates()
	previous, previousFound := detectionStore(locations).Load()
	obdDevice := known.obd
	if obdDevice == "" && previousFound {
		obdDevice = previous.OBD
	}
	candidates := make([]string, 0, len(allCandidates))
	for _, candidate := range allCandidates {
		if obdDevice != "" && agentruntime.ValidateDistinctDevices(obdDevice, candidate) != nil {
			continue
		}
		candidates = append(candidates, candidate)
	}
	// The OBD path is excluded by name above only once one has been detected. A
	// vehicle source that is opening or holding a port says so regardless, which
	// is what covers the case where nothing has been detected yet.

	result := resolvedDevices{gps: hardware.GPS, obd: obdDevice, modem: hardware.Modem}
	result.reports = sweepUnownedPorts(positionRole, candidates, ownership, func(report providers.PortReport) {
		fmt.Fprintf(os.Stderr, "position probe %s -> %s\n", report.Device, describePort(report))
	})
	probedGPS, _, probedModem := providers.SelectRoles(result.reports)
	if hardware.GPS == store.Auto {
		result.gps = probedGPS
	}
	if result.modem == "" {
		result.modem = probedModem
	}
	if result.gps == store.Off || result.gps == store.Auto {
		result.gps = ""
	}
	if result.modem == store.Off {
		result.modem = ""
	}
	if result.gps != "" && result.modem == "" {
		result.modem = modemPath(result.reports, result.gps)
	}
	result.gpsStreams = providers.StreamsNMEA(result.reports, result.gps)

	detection := store.Detection{
		At:         time.Now().UTC().Format(time.RFC3339),
		GPS:        result.gps,
		OBD:        obdDevice,
		Modem:      result.modem,
		GPSStreams: result.gpsStreams,
		Candidates: allCandidates,
		Ports:      result.reports,
	}
	// A normal failed refresh keeps the proven recovery route. Deliberate modem
	// and USB resets forget the cache before arriving here, so their failed
	// rediscovery is stored as empty and cannot resurrect stale paths.
	if previousFound && previous.Usable(allCandidates) {
		if detection.GPS == "" {
			detection.GPS = previous.GPS
			detection.GPSStreams = previous.GPSStreams
		}
		if detection.Modem == "" {
			detection.Modem = previous.Modem
		}
	}
	if err := detectionStore(locations).Save(detection); err != nil {
		fmt.Fprintln(os.Stderr, "Could not record recovered position device:", err)
	}
	return result
}

func reprobeVehicleDevice(locations paths, gpsDevice string, ownership *serialOwnership) (string, error) {
	serialSweep.Lock()
	defer serialSweep.Unlock()
	previous, _ := detectionStore(locations).Load()
	owned := ownership.heldByOthers(vehicleRole)
	// The adapter that worked last time is asked first, alone. Sweeping every
	// port on every retry is seconds of opening and writing to hardware another
	// source may be using, to rediscover a device that never moved; it is worth
	// doing only once that device is gone or has stopped answering as an adapter.
	if known := knownVehicleDevice(previous, gpsDevice, owned); known != "" {
		report := probeKnownPort(known)
		fmt.Fprintf(os.Stderr, "vehicle probe %s -> %s\n", report.Device, describePort(report))
		if report.Role == providers.RoleELM {
			return known, nil
		}
		fmt.Fprintf(os.Stderr, "vehicle probe %s no longer answers as an adapter; sweeping\n", known)
	}
	allCandidates := serialCandidates()
	candidates := make([]string, 0, len(allCandidates))
	for _, candidate := range allCandidates {
		if agentruntime.ValidateDistinctDevices(gpsDevice, candidate) == nil {
			candidates = append(candidates, candidate)
		}
	}
	reports := sweepUnownedPorts(vehicleRole, candidates, ownership, func(report providers.PortReport) {
		fmt.Fprintf(os.Stderr, "vehicle probe %s -> %s\n", report.Device, describePort(report))
	})
	_, obdDevice, _ := providers.SelectRoles(reports)
	if obdDevice == "" && previous.OBD != "" {
		obdDevice = retryKnownVehicleDevice(previous.OBD, candidates, reports)
	}
	if obdDevice == "" {
		return "", fmt.Errorf(
			"no OBD device found while probing /dev/serial/by-id/*, /dev/ttyUSB*, /dev/ttyACM*",
		)
	}
	detection := previous
	detection.At = time.Now().UTC().Format(time.RFC3339)
	detection.OBD = obdDevice
	detection.Candidates = allCandidates
	detection.Ports = reports
	if detection.GPS == "" {
		detection.GPS = gpsDevice
	}
	if err := detectionStore(locations).Save(detection); err != nil {
		fmt.Fprintln(os.Stderr, "Could not record recovered vehicle device:", err)
	}
	return obdDevice, nil
}

// retryKnownVehicleDevice gives the port that used to be the adapter one more
// chance before the sweep is declared a failure. An adapter reset by the service
// that just stopped needs a moment before it answers again, and calling that a
// missing device sends the agent looking for hardware that never moved.
// knownVehicleDevice names the adapter a retry should try before sweeping: the
// one the last detection recorded, when it still exists and is neither the GPS
// path nor a port the position source is holding.
func knownVehicleDevice(previous store.Detection, gpsDevice string, owned []string) string {
	known := previous.OBD
	if known == "" || !fileExists(known) {
		return ""
	}
	if agentruntime.ValidateDistinctDevices(gpsDevice, known) != nil {
		return ""
	}
	if len(withoutOwnedPorts([]string{known}, owned)) == 0 {
		return ""
	}
	return known
}

func retryKnownVehicleDevice(known string, candidates []string, reports []providers.PortReport) string {
	if !slices.Contains(candidates, known) {
		return ""
	}
	for _, report := range reports {
		if report.Device == known && report.Role != providers.RoleUnknown {
			return ""
		}
	}
	fmt.Fprintf(os.Stderr, "vehicle probe %s read as unknown; retrying the port it used last\n", known)
	report := probeKnownPort(known)
	fmt.Fprintf(os.Stderr, "vehicle probe %s -> %s\n", report.Device, describePort(report))
	if report.Role == providers.RoleELM {
		return known
	}
	return ""
}

// fromDetection rebuilds a selection from the stored answer. An explicit choice in
// the hardware file still wins: the cache only ever answers for "auto".
func fromDetection(hardware store.Hardware, detection store.Detection) resolvedDevices {
	result := resolvedDevices{gps: hardware.GPS, obd: hardware.OBD, modem: hardware.Modem}
	if hardware.GPS == store.Auto {
		result.gps = detection.GPS
	}
	if hardware.OBD == store.Auto {
		result.obd = detection.OBD
	}
	if result.modem == "" {
		result.modem = detection.Modem
	}
	for _, field := range []*string{&result.gps, &result.obd, &result.modem} {
		if *field == store.Off || *field == store.Auto {
			*field = ""
		}
	}
	result.gpsStreams = detection.GPSStreams && result.gps == detection.GPS
	return result
}

// describePort names every capability a port has rather than only the one it is
// filed under, because the useful fact is often the second one: an interface that
// streams NMEA and also accepts AT is the one that can switch the receiver on.
func describePort(report providers.PortReport) string {
	if report.Error != "" {
		return string(providers.RoleUnknown) + ": " + report.Error
	}
	found := []string{}
	for _, capability := range []struct {
		present bool
		name    string
	}{{report.NMEA, "nmea"}, {report.ELM, "elm"}, {report.Modem, "modem"}} {
		if capability.present {
			found = append(found, capability.name)
		}
	}
	if len(found) == 0 {
		return string(providers.RoleUnknown)
	}
	described := strings.Join(found, "+")
	if report.Identity != "" {
		described += ": " + report.Identity
	}
	return described
}

// modemPath decides whether the GPS path is itself a modem control port.
//
// The sweep has almost always just classified it, and reusing that answer is the
// point: reopening a serial port this process closed microseconds earlier is what
// a cellular module's multi-interface USB driver handles worst, and on a SIM7600
// it wedged the open, taking every diagnostic command down with it. Only a path
// the sweep never saw, meaning one configured explicitly rather than found, is
// probed here.
func modemPath(reports []providers.PortReport, device string) string {
	for _, report := range reports {
		if report.Device != device {
			continue
		}
		if report.Modem {
			return device
		}
		return ""
	}
	if providers.ProbeDevice(device).Modem {
		return device
	}
	return ""
}

// forceHardware runs a hardware command anyway, for an operator who has a reason
// to accept a reading they cannot trust.
var forceHardware bool

// requireExclusiveHardware refuses to touch hardware the service is holding.
//
// This was a warning, which was not enough. Root is exempt from the exclusive
// access flag that would otherwise refuse the second open, so both processes
// succeed and then split one byte stream between them. The result is not degraded
// but arbitrary: across two runs seconds apart the same adapter identified itself,
// then timed out, while a modem interface did the reverse. A reading nobody can
// trust is worse than no reading, because it gets acted on.
func requireExclusiveHardware() error {
	if forceHardware || !agentsystem.ServiceRunning() {
		return nil
	}
	return fmt.Errorf(`%s is running and holds the serial ports.

Both processes would read the same stream and neither would get all of it, so the
result would be arbitrary rather than merely incomplete. Stop the service, take the
reading, then start it again:

  sudo systemctl stop carhibou-agent
  sudo carhibou-agent %s
  sudo systemctl start carhibou-agent

Pass --force before the command to read anyway`, agentsystem.ServiceName, strings.Join(os.Args[1:], " "))
}

// startPosition prepares the GPS source, switching the receiver on first.
//
// A module that boots with GNSS powered down publishes nothing at all, so without
// the enable step the agent would wait forever for a fix the hardware was never
// asked to produce. When the position source is the modem control port itself, the
// same handle then answers position over AT.
func startPosition(devices resolvedDevices, samplingSeconds int) (agentruntime.PositionProvider, func(), error) {
	if devices.gps == "" {
		return agentruntime.EmptyPosition{}, func() {}, nil
	}
	// A GPS path that publishes sentences is proof the receiver is already on, so
	// there is nothing to switch on and no reason to open the control port at all.
	// Doing it anyway asked a module that was plainly working whether it was, and
	// reported a failure to enable something already enabled — on hardware whose
	// control interface answers only sometimes.
	if devices.modem != "" && !devices.gpsStreams {
		modem := providers.NewModemPort(devices.modem)
		enabled, err := modem.GNSSEnabled()
		if err == nil && !enabled {
			if _, enableErr := modem.EnableGNSS(); enableErr != nil {
				fmt.Fprintln(os.Stderr, "GNSS enable failed:", enableErr)
			}
		}
		// Nothing is streaming, so the control port is the position source too:
		// it can still answer a fix over AT.
		return modem, modem.Close, nil
	}
	provider := providers.NewNMEAProvider(devices.gps)
	// Tolerate a couple of missed receiver updates, no more. Holding a fix for
	// much longer than the sampling interval reports where the vehicle was, not
	// where it is: ten stale seconds is nearly three hundred metres at motorway
	// speed.
	if window := time.Duration(2*samplingSeconds) * time.Second; window > provider.MaxAge {
		provider.MaxAge = window
	}
	return provider, provider.Close, nil
}

// servicePositionAcquirer keeps the position source replaceable for the life of
// the service.
//
// A cellular module can wedge, cold-boot, and come back on different interface
// numbers with its receiver switched off. Resolving the device once at startup
// meant that took the agent's position away until somebody restarted it, and the
// heartbeat never said so. Every retry re-probes and switches the receiver back
// on before trying again.
func servicePositionAcquirer(
	hardware store.Hardware,
	locations paths,
	initial resolvedDevices,
	samplingSeconds int,
	ownership *serialOwnership,
) agentruntime.PositionAcquirer {
	recovery := newPositionRecovery(hardware, locations, initial, samplingSeconds, ownership)
	return recovery.acquire
}

const (
	physicalRecoveryCooldown = usbrecovery.Cooldown
	moduleRecoverySettle     = 8 * time.Second
)

// positionRecovery is the ordered recovery policy for a position source. The
// policy is kept separate from the retrying owner: that owner decides *when* to
// retry without blocking telemetry, while this type decides the least invasive
// hardware action that can make the next provider useful.
type positionRecovery struct {
	hardware        store.Hardware
	locations       paths
	devices         resolvedDevices
	samplingSeconds int
	attempted       bool
	missingAttempts int
	lastUSBReset    time.Time

	ownership     *serialOwnership
	resolve       func(store.Hardware, paths, bool) resolvedDevices
	reprobe       func(store.Hardware, paths, resolvedDevices, *serialOwnership) resolvedDevices
	start         func(resolvedDevices, int) (agentruntime.PositionProvider, func(), error)
	restartGNSS   func(resolvedDevices) error
	restartModule func(resolvedDevices) error
	// resetUSB is given the position devices the agent is configured with and the
	// wider list of ttys the module may have re-enumerated onto. Only the first
	// decides what may be reset.
	resetUSB   func(configured, candidates []string) (usbrecovery.Device, error)
	candidates func() []string
	forget     func()
	now        func() time.Time
	sleep      func(time.Duration)
}

func newPositionRecovery(
	hardware store.Hardware,
	locations paths,
	initial resolvedDevices,
	samplingSeconds int,
	ownership *serialOwnership,
) *positionRecovery {
	return &positionRecovery{
		hardware:        hardware,
		locations:       locations,
		devices:         initial,
		samplingSeconds: samplingSeconds,
		ownership:       ownership,
		resolve:         resolveDevices,
		reprobe:         resolvePositionDevices,
		start:           startPosition,
		restartGNSS:     restartStreamingGNSS,
		restartModule:   restartSIMComModule,
		resetUSB: func(configured, candidates []string) (usbrecovery.Device, error) {
			// The candidate list is deliberately wide, because a module can come
			// back on different ttyUSB numbers. The allowed set keeps that width
			// honest: it is resolved from the configured receiver and control
			// port, so a sweep across every tty on the host cannot reach the OBD
			// adapter or anything else that happens to be plugged in.
			allowed, _ := usbRecoveryTargets(configured)
			return usbrecovery.New(usbrecovery.Config{AllowedDevices: allowed}).ResetCandidates(candidates)
		},
		candidates: store.SerialCandidates,
		forget:     func() { detectionStore(locations).Forget() },
		now:        time.Now,
		sleep:      time.Sleep,
	}
}

func (recovery *positionRecovery) acquire() (agentruntime.PositionProvider, error) {
	if recovery.hardware.GPS == store.Off {
		return nil, fmt.Errorf("position source is disabled in hardware configuration")
	}

	if recovery.hardware.GPS == store.Auto {
		recovery.devices = mergeResolvedDevices(
			recovery.devices,
			recovery.resolve(recovery.hardware, recovery.locations, false),
		)
		// A structurally valid cache with no GPS answer is not a recovery
		// answer. Isolated probing makes a fresh sweep safe to repeat: a timed
		// out child is gone before the next port is touched.
		if recovery.devices.gps == "" || recovery.devices.gpsStreams && recovery.devices.modem == "" {
			recovery.devices = mergeResolvedDevices(
				recovery.devices,
				recovery.reprobe(recovery.hardware, recovery.locations, recovery.devices, recovery.ownership),
			)
		}
	}

	if recovery.attempted && recovery.devices.gpsStreams {
		if err := recovery.restartGNSS(recovery.devices); err != nil {
			fmt.Fprintln(os.Stderr, "GNSS receiver-only restart failed:", err)
			if moduleErr := recovery.restartModule(recovery.devices); moduleErr == nil {
				fmt.Fprintln(os.Stderr, "SIMCom modem restart accepted; waiting for its serial interfaces")
				if !recovery.rediscoverAfterReset() {
					recovery.tryUSBReset()
				}
			} else {
				fmt.Fprintln(os.Stderr, "SIMCom modem restart failed:", moduleErr)
				recovery.tryUSBReset()
			}
		}
	}
	recovery.attempted = true

	if recovery.devices.gps == "" {
		recovery.missingAttempts++
		// Give an initially enumerating modem one ordinary retry before
		// resetting anything. On the next miss, the complete isolated sweep has
		// proved that none of its interfaces currently answers.
		if recovery.missingAttempts >= 2 {
			recovery.tryUSBReset()
		}
	} else {
		recovery.missingAttempts = 0
	}

	if recovery.devices.gps == "" {
		return nil, fmt.Errorf(
			"no GPS device found while probing /dev/serial/by-id/*, /dev/ttyUSB*, /dev/ttyACM*",
		)
	}
	// Declared before the port is opened, so a vehicle sweep starting in the same
	// instant skips it rather than reporting it busy and failing an acquisition
	// that had nothing wrong with it.
	recovery.ownership.claim(positionRole, recovery.devices.gps, recovery.devices.modem)
	provider, _, err := recovery.start(recovery.devices, recovery.samplingSeconds)
	return provider, err
}

func (recovery *positionRecovery) tryUSBReset() {
	now := recovery.now()
	if !recovery.lastUSBReset.IsZero() && now.Sub(recovery.lastUSBReset) < physicalRecoveryCooldown {
		return
	}
	recovery.lastUSBReset = now
	configured := compactStrings([]string{recovery.devices.gps, recovery.devices.modem})
	candidates := append(append([]string{}, configured...), recovery.candidates()...)
	device, err := recovery.resetUSB(configured, compactStrings(candidates))
	if err != nil {
		fmt.Fprintln(os.Stderr, "Automatic SIMCom USB recovery was not available:", err)
		return
	}
	fmt.Fprintf(
		os.Stderr,
		"Reset wedged SIMCom USB device %s on bus %03d device %03d; waiting for serial interfaces\n",
		device.ProductID,
		device.BusNumber,
		device.DeviceNumber,
	)
	recovery.rediscoverAfterReset()
}

func (recovery *positionRecovery) rediscoverAfterReset() bool {
	recovery.sleep(moduleRecoverySettle)
	recovery.forget()
	fresh := recovery.reprobe(recovery.hardware, recovery.locations, recovery.devices, recovery.ownership)
	recovery.devices = fresh
	return fresh.gps != ""
}

func compactStrings(values []string) []string {
	result := make([]string, 0, len(values))
	seen := map[string]bool{}
	for _, value := range values {
		if value == "" || seen[value] {
			continue
		}
		seen[value] = true
		result = append(result, value)
	}
	return result
}

func mergeResolvedDevices(previous, fresh resolvedDevices) resolvedDevices {
	if fresh.gps != "" {
		previous.gps = fresh.gps
		previous.gpsStreams = fresh.gpsStreams
	}
	if fresh.obd != "" {
		previous.obd = fresh.obd
	}
	if fresh.modem != "" {
		previous.modem = fresh.modem
	}
	if len(fresh.reports) > 0 {
		previous.reports = fresh.reports
	}
	return previous
}

func restartStreamingGNSS(devices resolvedDevices) error {
	if devices.modem == "" {
		return fmt.Errorf("no known SIMCom control port")
	}
	modem := providers.NewModemPort(devices.modem)
	defer modem.Close()
	command, err := modem.RestartGNSS()
	if err != nil {
		return fmt.Errorf("through %s: %w", devices.modem, err)
	}
	fmt.Fprintln(os.Stderr, "GNSS receiver restarted through", devices.modem, "with", command)
	return nil
}

func restartSIMComModule(devices resolvedDevices) error {
	if devices.modem == "" {
		return fmt.Errorf("no known SIMCom control port")
	}
	modem := providers.NewModemPort(devices.modem)
	defer modem.Close()
	if err := modem.RestartModule(); err != nil {
		return fmt.Errorf("through %s: %w", devices.modem, err)
	}
	return nil
}

// commandConfig prints the accepted configuration, and with --pull fetches the
// server's current one first.
//
// The service syncs on its own schedule, so without this an interval changed in
// the interface leaves the operator watching an agent they cannot tell apart
// from one that failed to apply it.
func commandConfig(locations paths, arguments []string) error {
	flags := flag.NewFlagSet("config", flag.ContinueOnError)
	pull := flags.Bool("pull", false, "fetch the server configuration before printing")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	path := filepath.Join(locations.config, "config.json")
	if !*pull {
		return printFile(path)
	}
	credentials, err := loadCredentials(locations)
	if err != nil {
		return err
	}
	api, err := client.New(credentials.ServerURL, credentials.Credential, version, credentials.AllowInsecureHTTP)
	if err != nil {
		return err
	}
	fetched, err := api.FetchConfiguration()
	if err != nil {
		return err
	}
	// InstallIfNewer refuses a rollback and keeps the current file when the
	// version is unchanged, so pulling repeatedly is safe and says which it did.
	installed, err := (store.ConfigurationStore{Path: path}).InstallIfNewer(fetched)
	if err != nil {
		return err
	}
	printJSON(installed)
	if installed.Version == fetched.Version {
		fmt.Fprintf(os.Stderr, "Configuration version %d is current.\n", installed.Version)
	}
	// The running service holds its own copy in memory and reloads on its next
	// sync, so say so rather than implying the change already took effect.
	fmt.Fprintln(os.Stderr, "Apply it now with: sudo systemctl restart carhibou-agent")
	return nil
}

func commandRun(locations paths, arguments []string) error {
	flags := flag.NewFlagSet("run", flag.ContinueOnError)
	gpsOverride := flags.String("gps-device", "", "override GPS path")
	obdOverride := flags.String("obd-device", "", "override OBD path")
	syncSeconds := flags.Int("config-sync-seconds", 300, "configuration sync interval in seconds")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	if *syncSeconds <= 0 {
		return fmt.Errorf("--config-sync-seconds must be greater than zero")
	}
	watchdogStop := make(chan struct{})
	defer close(watchdogStop)
	notifier, notifyErr := newSystemdNotifier(os.Getenv("NOTIFY_SOCKET"))
	defer notifier.Close()
	if warning := systemdWatchdogWarning(os.Getenv("WATCHDOG_USEC"), os.Getenv("NOTIFY_SOCKET"), notifyErr); warning != "" {
		fmt.Fprintln(os.Stderr, warning)
	}
	startupNotifyStop := make(chan struct{})
	var stopStartupNotifier sync.Once
	stopStartup := func() { stopStartupNotifier.Do(func() { close(startupNotifyStop) }) }
	defer stopStartup()
	go runSystemdNotifier(startupNotifyStop, systemdNotifyInterval, notifier.Notify)
	credentials, err := loadCredentials(locations)
	if err != nil {
		return err
	}
	configurationStore := store.ConfigurationStore{Path: filepath.Join(locations.config, "config.json")}
	configuration, err := configurationStore.Load()
	if err != nil {
		return err
	}
	hardware, err := loadHardware(locations)
	if err != nil {
		return err
	}
	// The sweep records itself, so a start that reused the stored answer leaves it
	// as it was rather than restamping an answer it did not make.
	devices := resolveDevices(hardware, locations, false)
	if *gpsOverride != "" {
		devices.gps = *gpsOverride
	}
	if *obdOverride != "" {
		devices.obd = *obdOverride
	}
	gpsDevice := devices.gps
	if err := agentruntime.ValidateDistinctDevices(gpsDevice, devices.obd); err != nil {
		return err
	}
	api, err := client.New(credentials.ServerURL, credentials.Credential, version, credentials.AllowInsecureHTTP)
	if err != nil {
		return err
	}
	queue, err := store.OpenQueue(filepath.Join(locations.data, "queue.sqlite3"))
	if err != nil {
		return err
	}
	defer queue.Close()
	// The position source is acquired the way the vehicle source is: a failure
	// to find it is a state the agent reports and keeps retrying, not a reason to
	// exit. A module that wedges overnight and re-enumerates in the morning is
	// picked up without anybody restarting the service.
	ownership := newSerialOwnership()
	journal := func(line string) { fmt.Fprintln(os.Stderr, line) }
	position := agentruntime.NewRetryingPositionProvider(
		servicePositionAcquirer(hardware, locations, devices, configuration.Sampling.Longest(), ownership),
	)
	position.SetReporter(journal)
	position.Start()
	defer position.Close()
	if err := validateVehicleConfiguration(configuration); err != nil {
		return err
	}
	var configurationMutex sync.RWMutex
	currentConfiguration := func() store.Configuration {
		configurationMutex.RLock()
		defer configurationMutex.RUnlock()
		return configuration
	}
	acquireVehicle := serviceVehicleAcquirer(
		hardware,
		locations,
		gpsDevice,
		devices.obd,
		*obdOverride,
		currentConfiguration,
		ownership,
	)
	vehicle := agentruntime.NewRetryingVehicleProvider(acquireVehicle)
	vehicle.SetReporter(journal)
	vehicle.Start()
	defer vehicle.Close()
	sequence, _ := agentruntime.LastSequence(queue)
	agent := &agentruntime.Agent{Queue: queue, Client: api, Position: position, Vehicle: vehicle, BootID: model.NewUUID(), Sequence: sequence}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	var loopHeartbeat atomic.Int64
	heartbeat := func() {
		loopHeartbeat.Store(time.Now().UnixNano())
		notifier.Notify()
	}
	heartbeat()
	go runLoopWatchdog(
		&loopHeartbeat, time.Second, dumpAllStacks,
		func(stack []byte) { _, _ = os.Stderr.Write(stack) }, os.Exit, watchdogStop,
	)
	stopStartup()
	nextSample, nextUpload, nextSync := time.Now(), time.Now(), time.Now()
	for {
		heartbeat()
		select {
		case <-ctx.Done():
			return nil
		default:
		}
		now := time.Now()
		if !now.Before(nextSync) {
			remote, fetchErr := api.FetchConfiguration()
			// The fetch can spend its whole request timeout, and applying a changed
			// configuration below tears the vehicle session down inline, which can
			// itself take the better part of a minute on a silent bus. Each of
			// those gets its own heartbeat so neither has to fit inside the
			// other's share of the watchdog limit.
			heartbeat()
			if fetchErr == nil {
				candidate, installErr := configurationStore.InstallIfNewer(remote)
				if installErr == nil {
					if !reflect.DeepEqual(candidate, configuration) {
						if validationErr := validateVehicleConfiguration(candidate); validationErr == nil {
							configurationMutex.Lock()
							configuration = candidate
							configurationMutex.Unlock()
							vehicle.Reset()
						} else {
							fmt.Fprintln(os.Stderr, "Configuration sync retained last-known-good:", validationErr)
						}
					}
				} else {
					fmt.Fprintln(os.Stderr, "Configuration sync retained last-known-good:", installErr)
				}
			} else if api.ShouldReport(fetchErr) {
				fmt.Fprintln(os.Stderr, fetchErr)
			}
			nextSync = now.Add(time.Duration(*syncSeconds) * time.Second)
			// And the upload below can take another request timeout before its
			// first chunk finishes, so the teardown above does not share a budget
			// with it either.
			heartbeat()
		}
		// A meaningful transition is reported when it happens rather than at the
		// next cadence deadline, and the upload that carries it is flushed with
		// it: a charge that started at 02:00 is of no use first seen at 02:10.
		event := agent.PendingEvent()
		if event == "" {
			// A vehicle whose source reports no speed still moves, and the only
			// witness to that is its own displacement.
			event = agent.MotionEvent(now)
		}
		if event != "" || !now.Before(nextSample) {
			var collectErr error
			nextSample, nextUpload, collectErr = collectAtCadence(agent, configuration, now, nextUpload)
			if collectErr != nil {
				fmt.Fprintln(os.Stderr, "Collection failed:", collectErr)
			}
		}
		if !now.Before(nextUpload) {
			if _, err := agent.Upload(heartbeat); err != nil && api.ShouldReport(err) {
				fmt.Fprintln(os.Stderr, err)
			}
			nextUpload = now.Add(time.Duration(configuration.Upload.Seconds(agent.InUse)) * time.Second)
		}
		time.Sleep(250 * time.Millisecond)
	}
}

func runLoopWatchdog(
	heartbeat *atomic.Int64,
	checkEvery time.Duration,
	dump func() []byte,
	write func([]byte),
	exit func(int),
	stop <-chan struct{},
) {
	ticker := time.NewTicker(checkEvery)
	defer ticker.Stop()
	for {
		select {
		case <-stop:
			return
		case <-ticker.C:
			if time.Since(time.Unix(0, heartbeat.Load())) <= loopWatchdogLimit {
				continue
			}
			write(dump())
			exit(1)
			return
		}
	}
}

func runSystemdNotifier(stop <-chan struct{}, interval time.Duration, notify func()) {
	notify()
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-stop:
			return
		case <-ticker.C:
			notify()
		}
	}
}

func dumpAllStacks() []byte {
	buffer := make([]byte, 1<<20)
	count := runtime.Stack(buffer, true)
	return append([]byte("agent loop watchdog expired; goroutine stacks follow\n"), buffer[:count]...)
}

type systemdNotifier struct {
	connection *net.UnixConn
}

func newSystemdNotifier(socket string) (*systemdNotifier, error) {
	notifier := &systemdNotifier{}
	if socket == "" {
		return notifier, nil
	}
	if strings.HasPrefix(socket, "@") {
		socket = "\x00" + socket[1:]
	}
	connection, err := net.DialUnix("unixgram", nil, &net.UnixAddr{Name: socket, Net: "unixgram"})
	if err != nil {
		return notifier, err
	}
	notifier.connection = connection
	return notifier, nil
}

func (notifier *systemdNotifier) Notify() {
	if notifier.connection != nil {
		_, _ = notifier.connection.Write([]byte("WATCHDOG=1"))
	}
}

func (notifier *systemdNotifier) Close() {
	if notifier.connection != nil {
		_ = notifier.connection.Close()
	}
}

func systemdWatchdogWarning(watchdogUsec, socket string, notifyErr error) string {
	if notifyErr != nil {
		return "Warning: systemd watchdog notifications are unavailable: " + notifyErr.Error()
	}
	if watchdogUsec != "" && socket == "" {
		return "Warning: systemd expects watchdog notifications but NOTIFY_SOCKET is absent"
	}
	return ""
}

func reportingInterval(configuration store.Configuration, inUse bool) int {
	return max(configuration.Sampling.Seconds(inUse), configuration.Upload.Seconds(inUse))
}

func collectAtCadence(
	agent *agentruntime.Agent,
	configuration store.Configuration,
	now time.Time,
	nextUpload time.Time,
) (time.Time, time.Time, error) {
	agent.DrivingReportingInterval = reportingInterval(configuration, true)
	agent.ParkedReportingInterval = reportingInterval(configuration, false)
	wasInUse := agent.InUse
	sample, err := agent.Collect()
	nextSample := now.Add(time.Duration(configuration.Sampling.Seconds(agent.InUse)) * time.Second)
	if _, triggered := sample.Agent["sample_trigger"]; triggered {
		nextUpload = now
	}
	if wasInUse != agent.InUse {
		newDeadline := now.Add(time.Duration(configuration.Upload.Seconds(agent.InUse)) * time.Second)
		if newDeadline.Before(nextUpload) {
			nextUpload = newDeadline
		}
	}
	return nextSample, nextUpload, err
}

func vehicleProvider(
	device string,
	configuration store.Configuration,
	resetUSB func(string) error,
) (agentruntime.VehicleProvider, error) {
	decoder, err := vehicleProfileDecoder(configuration)
	if err != nil {
		return nil, err
	}
	if device == "" {
		return agentruntime.EmptyVehicle{}, nil
	}
	adapter := providers.NewOBDAdapter(device)
	if decoder == nil {
		return providers.NewStandardOBDProvider(adapter), nil
	}
	provider := providers.NewProfileProvider(adapter, decoder)
	provider.SetSamplingInterval(time.Duration(configuration.Sampling.DefaultSeconds) * time.Second)
	provider.SetUSBRecovery(resetUSB)
	return provider, nil
}

// resetOBDDevice resets the adapter the agent was configured with, and only it.
// The allowed set is resolved from that very tty, so the guard that remains is
// the resolver's own: the nearest USB ancestor, never a hub.
func resetOBDDevice(device string) error {
	resolver := usbrecovery.New(usbrecovery.Config{})
	identified, err := resolver.Identify(device)
	if err != nil {
		return err
	}
	_, err = usbrecovery.New(usbrecovery.Config{
		AllowedDevices: []usbrecovery.DeviceID{identified.ID()},
	}).ResetTTY(device)
	return err
}

func cooledDownOBDResetter(reset func(string) error, now func() time.Time) func(string) error {
	var mutex sync.Mutex
	var lastReset time.Time
	return func(device string) error {
		mutex.Lock()
		defer mutex.Unlock()
		at := now()
		if elapsed := at.Sub(lastReset); !lastReset.IsZero() && elapsed < physicalRecoveryCooldown {
			// Reporting the skip rather than success is what lets the caller's
			// diagnosis name the rung it stopped on. Returning nil said the reset
			// had been performed, so a device that was never touched read as one
			// that a physical reset had failed to revive.
			return fmt.Errorf("%w: the last one was %s ago and they are at least %s apart",
				usbrecovery.ErrCoolingDown, elapsed.Round(time.Second), physicalRecoveryCooldown)
		}
		lastReset = at
		return reset(device)
	}
}

func vehicleProfileDecoder(configuration store.Configuration) (*profile.DecoderEngine, error) {
	if configuration.VehicleProfile == nil {
		return nil, nil
	}
	if len(configuration.VehicleProfileDefinition) == 0 || string(configuration.VehicleProfileDefinition) == "null" {
		return nil, fmt.Errorf("selected profile has no server definition")
	}
	decoder, err := profile.ParseJSON(configuration.VehicleProfileDefinition)
	if err != nil {
		return nil, err
	}
	return decoder, nil
}

func validateVehicleConfiguration(configuration store.Configuration) error {
	_, err := vehicleProfileDecoder(configuration)
	return err
}

func serviceVehicleAcquirer(
	hardware store.Hardware,
	locations paths,
	gpsDevice string,
	initialDevice string,
	override string,
	configuration func() store.Configuration,
	ownership *serialOwnership,
) agentruntime.VehicleAcquirer {
	device := initialDevice
	firstAttempt := true
	resetUSB := cooledDownOBDResetter(resetOBDDevice, time.Now)
	// Claimed here rather than on the first attempt: the acquisition goroutine
	// may not be scheduled before the position source starts sweeping, and the
	// adapter this service was told to use is known already.
	if override != "" {
		device = override
	}
	ownership.claim(vehicleRole, device)
	return func() (agentruntime.VehicleProvider, error) {
		if override != "" {
			device = override
		} else if !firstAttempt && hardware.OBD == store.Auto {
			ownership.claim(vehicleRole)
			resolved, err := reprobeVehicleDevice(locations, gpsDevice, ownership)
			if err != nil {
				return nil, err
			}
			device = resolved
		}
		firstAttempt = false
		if device == "" {
			if hardware.OBD == store.Off {
				return nil, fmt.Errorf("vehicle source is disabled in hardware configuration")
			}
			return nil, fmt.Errorf(
				"no OBD device found while probing /dev/serial/by-id/*, /dev/ttyUSB*, /dev/ttyACM*",
			)
		}
		if err := agentruntime.ValidateDistinctDevices(gpsDevice, device); err != nil {
			return nil, err
		}
		// Declared before Start opens it, for the same reason the position side
		// declares its own: a sweep on the other goroutine must not walk over it.
		ownership.claim(vehicleRole, device)
		return buildVehicleProvider(device, configuration(), resetUSB)
	}
}

func loadCredentials(locations paths) (store.Credentials, error) {
	return agentsystem.LoadCredentials(filepath.Join(locations.config, "credentials.json"))
}

// configuredSerialPaths names the ttys the agent will use: the explicit
// selections, and for "auto" whatever the last resolution settled on.
//
// It probes only when the service is not running. A probe opens every serial
// port and writes to it, which is exactly what must not happen underneath a
// service that is holding two of them.
func configuredSerialPaths(locations paths) []string {
	hardware, err := loadHardware(locations)
	if err != nil {
		fmt.Fprintln(os.Stderr, "Could not read the hardware selection:", err)
		return nil
	}
	var devices resolvedDevices
	if agentsystem.ServiceRunning() {
		detection, found := detectionStore(locations).Load()
		if !found {
			return nil
		}
		devices = fromDetection(hardware, detection)
	} else {
		devices = resolveDevices(hardware, locations, false)
	}
	return compactStrings([]string{devices.gps, devices.obd, devices.modem})
}

// usbRecoveryTargets resolves serial paths to the physical USB devices that own
// them, and describes what each one turned out to be. The descriptions are the
// diagnostic: when nothing resolves, the operator needs to see the devices that
// are actually attached rather than a list of the ones this agent expected.
func usbRecoveryTargets(ttys []string) ([]usbrecovery.DeviceID, []string) {
	resolver := newUSBResolver()
	devices := []usbrecovery.DeviceID{}
	descriptions := []string{}
	seen := map[usbrecovery.DeviceID]bool{}
	for _, tty := range ttys {
		device, err := resolver.Identify(tty)
		if err != nil {
			descriptions = append(descriptions, fmt.Sprintf("%s: %v", tty, err))
			continue
		}
		descriptions = append(descriptions, fmt.Sprintf("%s: %s", tty, device))
		if identity := device.ID(); !seen[identity] {
			seen[identity] = true
			devices = append(devices, identity)
		}
	}
	return devices, descriptions
}

// grantUSBRecoveryRights gives the service group reset access to the devices the
// agent is configured with, whatever they are.
//
// The rule used to name vendors, which meant every different modem or adapter
// needed the agent changed before its last-resort reset would work. It now
// follows the configuration: each selected tty is resolved to the USB device
// that owns it and only those devices are granted.
func grantUSBRecoveryRights(ttys []string) {
	devices, descriptions := usbRecoveryTargets(ttys)
	if len(devices) == 0 {
		if len(ttys) == 0 {
			_, descriptions = usbRecoveryTargets(store.SerialCandidates())
		}
		fmt.Fprintln(os.Stderr, "Warning: no configured serial device resolved to a USB device, so no reset rights were granted.")
		for _, description := range descriptions {
			fmt.Fprintln(os.Stderr, "  "+description)
		}
		fmt.Fprintln(os.Stderr, "The agent runs normally; recovering wedged hardware may need a manual replug.")
		return
	}
	agentsystem.WarnIfUSBRecoveryRuleUnavailable(installUSBRecoveryRule(devices))
}

// newUSBResolver and installUSBRecoveryRule are the two host operations this
// grant performs. Tests replace them with a fake sysfs tree and a recorder,
// which is how the udev side is covered everywhere else.
var (
	newUSBResolver         = func() *usbrecovery.Recovery { return usbrecovery.New(usbrecovery.Config{}) }
	installUSBRecoveryRule = agentsystem.InstallUSBRecoveryRule
)

func loadHardware(locations paths) (store.Hardware, error) {
	return (store.HardwareStore{Path: filepath.Join(locations.config, "hardware.json")}).Load()
}
func readOptional(path string) []byte { content, _ := os.ReadFile(path); return content }
func fileExists(path string) bool     { return fileExistsFunc(path) }

// fileExistsFunc is the one filesystem question discovery asks. Tests replace it
// alongside the fake port set, which has no /dev entries of its own.
var fileExistsFunc = func(path string) bool { _, err := os.Stat(path); return err == nil }

func directoryWritable(path string) bool {
	if err := os.MkdirAll(path, 0o750); err != nil {
		return false
	}
	file, err := os.CreateTemp(path, ".doctor-*")
	if err != nil {
		return false
	}
	name := file.Name()
	file.Close()
	os.Remove(name)
	return true
}
func nullIfEmpty(value string) any {
	if value == "" {
		return nil
	}
	return value
}
func printJSON(value any) {
	encoded, _ := json.MarshalIndent(value, "", "  ")
	fmt.Println(string(encoded))
}
func printFile(path string) error {
	content, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	fmt.Print(string(content))
	return nil
}
func runAttached(name string, arguments ...string) error {
	command := exec.Command(name, arguments...)
	command.Stdin = os.Stdin
	command.Stdout = os.Stdout
	command.Stderr = os.Stderr
	return command.Run()
}
