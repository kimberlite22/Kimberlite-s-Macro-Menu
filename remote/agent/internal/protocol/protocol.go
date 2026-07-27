// Package protocol is the single Go-side definition of the agent <-> backend wire contract.
// It MUST stay in sync with remote/PROTOCOL.md and with the TypeScript backend's shared types.
// The agent depends only on the Go standard library, so nothing here imports third-party code.
package protocol

// CommandType is one of the fixed, whitelisted macro commands. This set is authoritative and must
// never grow to include raw coordinates, keystrokes, scripts, or arbitrary preset data. It mirrors
// the whitelist enforced by macro/remote_bridge.ahk (RemoteBridgeApplyCommand).
type CommandType string

const (
	CmdPause           CommandType = "PAUSE"
	CmdResume          CommandType = "RESUME"
	CmdStop            CommandType = "STOP"
	CmdSetActivePreset CommandType = "SET_ACTIVE_PRESET"
	CmdQueuePreset     CommandType = "QUEUE_PRESET"
)

// MaxArgBytes is the maximum length of a command argument (a preset name). The agent rejects a
// longer arg defensively even though the backend also validates it.
const MaxArgBytes = 200

// IsValidCommandType reports whether t is one of the whitelisted command types.
func IsValidCommandType(t CommandType) bool {
	switch t {
	case CmdPause, CmdResume, CmdStop, CmdSetActivePreset, CmdQueuePreset:
		return true
	default:
		return false
	}
}

// UsesArg reports whether the command type carries a (preset-name) argument.
func UsesArg(t CommandType) bool {
	return t == CmdSetActivePreset || t == CmdQueuePreset
}

// Agent-facing endpoint paths (see PROTOCOL.md section 3).
const (
	PathPair     = "/api/agent/pair"
	PathCommands = "/api/agent/commands"
	PathReport   = "/api/agent/report"
	PathVersion  = "/api/agent/version"
)

// StatusSchema is the schema version emitted by macro/remote_bridge.ahk in remote_status.json.
const StatusSchema = 1

// PairRequest redeems a one-time pairing code for a device token (POST /api/agent/pair).
type PairRequest struct {
	Code         string `json:"code"`
	Hostname     string `json:"hostname"`
	AgentVersion string `json:"agentVersion"`
	OS           string `json:"os"`
}

// PairResponse is returned on a successful pairing.
type PairResponse struct {
	DeviceToken string `json:"deviceToken"`
	DeviceID    string `json:"deviceId"`
	DeviceName  string `json:"deviceName"`
}

// Command is a single whitelisted command delivered to the agent (GET /api/agent/commands).
type Command struct {
	ID   string      `json:"id"`
	Type CommandType `json:"type"`
	Arg  string      `json:"arg"`
}

// CommandsResponse is the long-poll result; Commands is empty on timeout.
type CommandsResponse struct {
	Commands []Command `json:"commands"`
}

// StatusSnapshot mirrors remote_status.json (schema 1) plus the agent-derived MacroOnline flag.
// The agent parses remote_status.json into this struct and forwards it in a ReportRequest.
type StatusSnapshot struct {
	MacroOnline bool `json:"macroOnline"`

	Schema    int    `json:"schema"`
	Timestamp string `json:"timestamp"`
	State     string `json:"state"`
	Running   bool   `json:"running"`
	Paused    bool   `json:"paused"`
	DryRun    bool   `json:"dryRun"`

	ActivePreset  string `json:"activePreset"`
	RunningPreset string `json:"runningPreset"`
	QueuedPreset  string `json:"queuedPreset"`

	CurrentMap    string `json:"currentMap"`
	CurrentScreen string `json:"currentScreen"`
	CurrentStep   string `json:"currentStep"`

	CycleCount       int `json:"cycleCount"`
	StepRepeatCount  int `json:"stepRepeatCount"`
	StartRepeatCount int `json:"startRepeatCount"`
	VictoryCount     int `json:"victoryCount"`
	DefeatCount      int `json:"defeatCount"`
}

// LogLine is one new line tailed from macro_log.txt. Seq is monotonic per device.
type LogLine struct {
	Seq  int64  `json:"seq"`
	Line string `json:"line"`
}

// Ack reports the result of a command back to the backend (echoing the command id).
type Ack struct {
	CommandID string `json:"commandId"`
	OK        bool   `json:"ok"`
	Message   string `json:"message"`
}

// ReportRequest is the agent's phone-home write (POST /api/agent/report). Every field is optional;
// a bare heartbeat sends only Status.
type ReportRequest struct {
	Status *StatusSnapshot `json:"status,omitempty"`
	Logs   []LogLine       `json:"logs,omitempty"`
	Acks   []Ack           `json:"acks,omitempty"`
}

// ReportResponse acknowledges a report; NextPollMs is an optional pacing hint.
type ReportResponse struct {
	OK                 bool   `json:"ok"`
	NextPollMs         int    `json:"nextPollMs,omitempty"`
	LatestAgentVersion string `json:"latestAgentVersion,omitempty"`
}

// VersionResponse contains the versions supported by the backend for the agent.
type VersionResponse struct {
	Latest       string `json:"latest"`
	MinSupported string `json:"minSupported"`
}
