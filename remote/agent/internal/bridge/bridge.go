// Package bridge implements the file bridge between the agent and the AHK macro.
package bridge

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/animeexpedition/agent/internal/protocol"
)

const statusTimestampLayout = "2006-01-02 15:04:05"

// ErrAckTimeout indicates that a command was published but the macro did not
// acknowledge it before the requested timeout.
var ErrAckTimeout = errors.New("macro acknowledgement timed out")

// Bridge is a file-system connection to one macro directory.
type Bridge struct {
	macroDir string
}

// New creates a bridge for the supplied macro script directory.
func New(macroDir string) *Bridge {
	return &Bridge{macroDir: macroDir}
}

// ReadStatus returns the macro status snapshot and derives its liveness from
// the locally formatted timestamp. A missing or malformed status file is an
// offline snapshot rather than an error because the macro may be closed.
func (b *Bridge) ReadStatus() (*protocol.StatusSnapshot, error) {
	path := filepath.Join(b.macroDir, "remote_status.json")
	data, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return &protocol.StatusSnapshot{}, nil
	}
	if err != nil {
		return &protocol.StatusSnapshot{}, err
	}
	data = []byte(strings.TrimPrefix(string(data), "\ufeff"))
	if len(strings.TrimSpace(string(data))) == 0 {
		return &protocol.StatusSnapshot{}, nil
	}

	var snapshot protocol.StatusSnapshot
	if err := json.Unmarshal(data, &snapshot); err != nil {
		return &protocol.StatusSnapshot{}, nil
	}
	stamp, err := time.ParseInLocation(statusTimestampLayout, snapshot.Timestamp, time.Local)
	if err != nil {
		return &protocol.StatusSnapshot{}, nil
	}
	snapshot.MacroOnline = time.Since(stamp) <= 5*time.Second
	return &snapshot, nil
}

// SendCommand validates and atomically publishes one command for the macro.
func (b *Bridge) SendCommand(cmd protocol.Command) error {
	if !protocol.IsValidCommandType(cmd.Type) {
		return fmt.Errorf("invalid command type %q", cmd.Type)
	}
	if len([]byte(cmd.Arg)) > protocol.MaxArgBytes {
		return fmt.Errorf("command argument exceeds %d bytes", protocol.MaxArgBytes)
	}
	path := filepath.Join(b.macroDir, "remote_cmd.txt")
	tmp := path + ".tmp"
	line := cmd.ID + "|" + string(cmd.Type) + "|" + cmd.Arg
	if err := os.WriteFile(tmp, []byte(line), 0o600); err != nil {
		return err
	}

	// The macro normally deletes the destination before the next command. If a
	// stale target remains, Windows requires removing it before os.Rename.
	if err := os.Remove(path); err != nil && !errors.Is(err, os.ErrNotExist) {
		_ = os.Remove(tmp)
		return err
	}
	if err := os.Rename(tmp, path); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	return nil
}

// WaitForAck waits for and consumes the acknowledgement matching token.
func (b *Bridge) WaitForAck(token string, timeout time.Duration) (protocol.Ack, error) {
	path := filepath.Join(b.macroDir, "remote_ack.txt")
	deadline := time.Now().Add(timeout)
	for {
		data, err := os.ReadFile(path)
		if err == nil {
			parts := strings.SplitN(strings.TrimSpace(string(data)), "|", 3)
			if len(parts) == 3 && parts[0] == token && (parts[1] == "ok" || parts[1] == "error") {
				ack := protocol.Ack{CommandID: token, OK: parts[1] == "ok", Message: parts[2]}
				if err := os.Remove(path); err != nil && !errors.Is(err, os.ErrNotExist) {
					return ack, err
				}
				return ack, nil
			}
		} else if !errors.Is(err, os.ErrNotExist) {
			return protocol.Ack{}, err
		}

		if time.Now().After(deadline) {
			return protocol.Ack{CommandID: token, OK: false, Message: "no ack from macro (offline?)"}, ErrAckTimeout
		}
		time.Sleep(100 * time.Millisecond)
	}
}

// LogTailer incrementally reads new complete lines from macro_log.txt.
type LogTailer struct {
	path        string
	initialized bool
	offset      int64
	partial     string
	nextSeq     int64
}

// TailLog creates a tailer whose first emitted line uses startSeq. Its returned
// sequence value is the next sequence number to persist and pass after restart.
func (b *Bridge) TailLog(startSeq int64) *LogTailer {
	return &LogTailer{path: filepath.Join(b.macroDir, "macro_log.txt"), nextSeq: startSeq}
}

// Poll returns only newly appended complete log lines and the next sequence number.
func (t *LogTailer) Poll() ([]protocol.LogLine, int64) {
	info, err := os.Stat(t.path)
	if errors.Is(err, os.ErrNotExist) {
		t.initialized = true
		t.offset = 0
		return nil, t.nextSeq
	}
	if err != nil {
		return nil, t.nextSeq
	}
	if !t.initialized {
		t.initialized = true
		t.offset = info.Size()
		return nil, t.nextSeq
	}
	if info.Size() < t.offset {
		t.offset = 0
		t.partial = ""
	}

	file, err := os.Open(t.path)
	if err != nil {
		return nil, t.nextSeq
	}
	defer file.Close()
	if _, err := file.Seek(t.offset, 0); err != nil {
		return nil, t.nextSeq
	}
	data, err := io.ReadAll(file)
	if err != nil {
		return nil, t.nextSeq
	}
	newData := data
	t.offset += int64(len(data))
	if len(newData) == 0 {
		return nil, t.nextSeq
	}

	text := t.partial + string(newData)
	chunks := strings.Split(text, "\n")
	t.partial = chunks[len(chunks)-1]
	chunks = chunks[:len(chunks)-1]
	lines := make([]protocol.LogLine, 0, len(chunks))
	for _, line := range chunks {
		lines = append(lines, protocol.LogLine{Seq: t.nextSeq, Line: strings.TrimSuffix(line, "\r")})
		t.nextSeq++
	}
	return lines, t.nextSeq
}
