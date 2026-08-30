package providers

import (
	"errors"
	"fmt"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
)

type ProtocolTrialResult struct {
	Code        string       `json:"code"`
	Description string       `json:"description"`
	BaudRate    int          `json:"baud_rate"`
	Trace       MonitorTrace `json:"trace"`
	Error       string       `json:"error,omitempty"`
}

type ProfileMonitorPreparation struct {
	InitialBaud        int                   `json:"initial_baud_rate"`
	FinalBaud          int                   `json:"final_baud_rate"`
	BaudFallbackReason string                `json:"baud_fallback_reason,omitempty"`
	ProtocolCode       string                `json:"protocol_code"`
	Protocol           string                `json:"protocol"`
	ProtocolTrials     []ProtocolTrialResult `json:"protocol_trials"`
	FilterCommands     []CommandExchange     `json:"filter_commands"`
	RestoredFilters    []CommandExchange     `json:"restored_filters,omitempty"`
	Filtered           MonitorTrace          `json:"filtered_stm"`
	Unfiltered         *MonitorTrace         `json:"unfiltered_stma,omitempty"`
	UseUnfiltered      bool                  `json:"use_unfiltered_monitor"`
	HardwareFilterGood bool                  `json:"hardware_filters_effective"`
}

// CANProtocolCount is how many protocols a full verification tries, so a caller
// can derive a sensible overall limit from its per-stage window.
func CANProtocolCount() int { return len(canProtocols) }

// ErrPreparationDeadline reports that preparation stopped between stages because
// the caller's overall deadline passed. What ran is still returned.
var ErrPreparationDeadline = errors.New("monitor preparation exceeded its deadline")

// PrepareProfileMonitor is shared by the service and obd-selftest so the
// diagnostic exercises the exact command order that production uses.
//
// progress may be nil. It names each stage as it starts, because every stage is
// several seconds of listening and the whole sequence is over a minute: without
// it the diagnostic is indistinguishable from a hang. deadline may be zero for
// no limit; it is checked between stages, so the overshoot is bounded by one
// verification window rather than by the remaining stages.
func PrepareProfileMonitor(
	adapter *OBDAdapter,
	canIDs []int,
	verificationWindow time.Duration,
	rawLineLimit int,
	inspectUnfiltered bool,
	onFrame func(model.CANFrame),
	progress func(string),
	deadline time.Time,
) (ProfileMonitorPreparation, error) {
	announce := func(stage string) {
		if progress != nil {
			progress(stage)
		}
	}
	expired := func() bool { return !deadline.IsZero() && time.Now().After(deadline) }
	result := ProfileMonitorPreparation{InitialBaud: adapter.BaudRate()}
	allowed := make(map[int]struct{}, len(canIDs))
	for _, canID := range canIDs {
		allowed[canID] = struct{}{}
	}
	profileFrame := func(frame model.CANFrame) {
		if _, ok := allowed[frame.CANID]; ok {
			onFrame(frame)
		}
	}

	trials, protocolCode, protocolDescription, filterCommands, err := inspectProtocols(
		adapter, canIDs, verificationWindow, rawLineLimit, profileFrame, announce, expired,
	)
	result.FilterCommands = filterCommands
	result.ProtocolTrials = append(result.ProtocolTrials, trials...)
	if err != nil {
		return result, err
	}
	result.ProtocolCode, result.Protocol = protocolCode, protocolDescription

	if result.InitialBaud != defaultOBDBaudRate && !sustainedCleanTraffic(trials) {
		result.BaudFallbackReason = "negotiated baud did not carry at least three clean CAN frames during protocol verification"
		announce(fmt.Sprintf("returning to %d baud and retrying protocol verification", defaultOBDBaudRate))
		if err := adapter.PreferDefaultBaud(); err != nil {
			return result, err
		}
		trials, protocolCode, protocolDescription, filterCommands, err = inspectProtocols(
			adapter, canIDs, verificationWindow, rawLineLimit, profileFrame, announce, expired,
		)
		result.FilterCommands = filterCommands
		result.ProtocolTrials = append(result.ProtocolTrials, trials...)
		if err != nil {
			return result, err
		}
		result.ProtocolCode, result.Protocol = protocolCode, protocolDescription
	}
	result.FinalBaud = adapter.BaudRate()

	if expired() {
		return result, ErrPreparationDeadline
	}
	announce(fmt.Sprintf("verifying hardware-filtered monitoring for %s", verificationWindow))
	result.Filtered, err = adapter.InspectMonitor(verificationWindow, false, rawLineLimit, profileFrame)
	if err != nil {
		return result, fmt.Errorf("filtered CAN verification stopped: %w", err)
	}
	if result.Filtered.Report.ParsedFrames > 0 && !inspectUnfiltered {
		result.HardwareFilterGood = true
		return result, nil
	}

	if expired() {
		return result, ErrPreparationDeadline
	}
	announce(fmt.Sprintf("verifying unfiltered monitoring for %s", verificationWindow))
	unfiltered, err := adapter.InspectMonitor(verificationWindow, true, rawLineLimit, profileFrame)
	result.Unfiltered = &unfiltered
	if err != nil {
		return result, fmt.Errorf("unfiltered CAN verification stopped: %w", err)
	}
	if result.Filtered.Report.ParsedFrames > 0 {
		result.HardwareFilterGood = true
		return result, nil
	}
	if unfiltered.Report.ParsedFrames > 0 {
		result.UseUnfiltered = true
		return result, nil
	}

	// STMA is documented as temporary, but reapplying the profile filters makes
	// the quiet-bus path independent of whether a particular firmware restores
	// them after the monitor stops.
	announce("restoring CAN filters")
	result.RestoredFilters, err = adapter.PassFiltersReport(canIDs)
	if err != nil {
		return result, fmt.Errorf("adapter did not restore the CAN filters: %w", err)
	}
	return result, nil
}

// inspectProtocols finds the protocol that carries this profile's frames.
//
// Filters are installed before each trial listens, because on at least one STN
// firmware a filtered monitor with no filters installed passes nothing at all
// rather than everything. Trials that listened first therefore heard silence on
// a wide-awake bus and proved only that the question had been asked backwards.
// Selecting a protocol needs no listening evidence, so the order that works on
// real hardware is select, filter, then listen.
func inspectProtocols(
	adapter *OBDAdapter,
	canIDs []int,
	window time.Duration,
	rawLineLimit int,
	onFrame func(model.CANFrame),
	announce func(string),
	expired func() bool,
) ([]ProtocolTrialResult, string, string, []CommandExchange, error) {
	trials := []ProtocolTrialResult{}
	filters := []CommandExchange{}
	for _, protocol := range canProtocols {
		if expired() {
			return trials, "", "", filters, ErrPreparationDeadline
		}
		announce(fmt.Sprintf("listening %s on %s (protocol %s)", window, protocol.description, protocol.code))
		trial := ProtocolTrialResult{
			Code: protocol.code, Description: protocol.description, BaudRate: adapter.BaudRate(),
		}
		if err := adapter.SelectProtocol(protocol.code); err != nil {
			trial.Error = err.Error()
			trials = append(trials, trial)
			continue
		}
		installed, err := adapter.PassFiltersReport(canIDs)
		if err != nil {
			trial.Error = err.Error()
			trials = append(trials, trial)
			return trials, "", "", installed, fmt.Errorf("adapter rejected the CAN filters: %w", err)
		}
		filters = installed
		trace, err := adapter.InspectMonitor(window, false, rawLineLimit, onFrame)
		trial.Trace = trace
		if err != nil {
			trial.Error = err.Error()
			trials = append(trials, trial)
			return trials, "", "", filters, fmt.Errorf("adapter stopped while testing protocol %s: %w", protocol.code, err)
		}
		trials = append(trials, trial)
		if trace.Report.ParsedFrames > 0 {
			return trials, protocol.code, protocol.description, filters, nil
		}
	}
	fallback := canProtocols[0]
	if err := adapter.SelectProtocol(fallback.code); err != nil {
		return trials, "", "", filters, fmt.Errorf("adapter rejected every CAN protocol: %w", err)
	}
	// The protocol changed, so the filters that belonged to the last trial did
	// not follow it.
	installed, err := adapter.PassFiltersReport(canIDs)
	if err != nil {
		return trials, "", "", installed, fmt.Errorf("adapter rejected the CAN filters: %w", err)
	}
	return trials, fallback.code, fallback.description, installed, nil
}

func sustainedCleanTraffic(trials []ProtocolTrialResult) bool {
	for _, trial := range trials {
		report := trial.Trace.Report
		if report.ParsedFrames >= 3 && !report.BufferFull && report.DataErrors == 0 &&
			report.AdapterErrors == 0 && report.MalformedFrames == 0 && !report.DroppedData {
			return true
		}
	}
	return false
}

func mergeMonitorReports(left, right MonitorReport) MonitorReport {
	return MonitorReport{
		ParsedFrames:    left.ParsedFrames + right.ParsedFrames,
		BufferFull:      left.BufferFull || right.BufferFull,
		DataErrors:      left.DataErrors + right.DataErrors,
		AdapterErrors:   left.AdapterErrors + right.AdapterErrors,
		MalformedFrames: left.MalformedFrames + right.MalformedFrames,
		DroppedData:     left.DroppedData || right.DroppedData,
	}
}

func preparationMonitorReport(preparation ProfileMonitorPreparation) MonitorReport {
	report := preparation.Filtered.Report
	for _, trial := range preparation.ProtocolTrials {
		report = mergeMonitorReports(report, trial.Trace.Report)
	}
	if preparation.Unfiltered != nil {
		report = mergeMonitorReports(report, preparation.Unfiltered.Report)
	}
	return report
}
