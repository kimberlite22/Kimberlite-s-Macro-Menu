package bridge

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/animeexpedition/agent/internal/protocol"
)

func TestSendCommandWritesProtocolLine(t *testing.T) {
	dir := t.TempDir()
	b := New(dir)
	cmd := protocol.Command{ID: "command-1", Type: protocol.CmdQueuePreset, Arg: "farm"}
	if err := b.SendCommand(cmd); err != nil {
		t.Fatalf("SendCommand: %v", err)
	}
	got, err := os.ReadFile(filepath.Join(dir, "remote_cmd.txt"))
	if err != nil {
		t.Fatalf("read command: %v", err)
	}
	if string(got) != "command-1|QUEUE_PRESET|farm" {
		t.Fatalf("command contents = %q", got)
	}
}

func TestReadStatusLiveness(t *testing.T) {
	dir := t.TempDir()
	b := New(dir)
	path := filepath.Join(dir, "remote_status.json")
	writeStatus := func(timestamp string) {
		t.Helper()
		content := `{"schema":1,"timestamp":"` + timestamp + `","state":"running"}`
		if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
			t.Fatal(err)
		}
	}

	fresh := time.Now().In(time.Local).Format(statusTimestampLayout)
	writeStatus(fresh)
	status, err := b.ReadStatus()
	if err != nil || !status.MacroOnline {
		t.Fatalf("fresh status = %#v, %v", status, err)
	}
	writeStatus(time.Now().Add(-10 * time.Second).In(time.Local).Format(statusTimestampLayout))
	status, err = b.ReadStatus()
	if err != nil || status.MacroOnline {
		t.Fatalf("stale status = %#v, %v", status, err)
	}
	if err := os.Remove(path); err != nil {
		t.Fatal(err)
	}
	status, err = b.ReadStatus()
	if err != nil || status.MacroOnline {
		t.Fatalf("missing status = %#v, %v", status, err)
	}
}

func TestTailLogOnlyNewLinesAndTruncation(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "macro_log.txt")
	if err := os.WriteFile(path, []byte("old\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	tailer := New(dir).TailLog(10)
	if lines, _ := tailer.Poll(); len(lines) != 0 {
		t.Fatalf("initial lines = %#v", lines)
	}
	file, err := os.OpenFile(path, os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := file.WriteString("first\npartial"); err != nil {
		t.Fatal(err)
	}
	if err := file.Close(); err != nil {
		t.Fatal(err)
	}
	lines, next := tailer.Poll()
	if len(lines) != 1 || lines[0].Seq != 10 || lines[0].Line != "first" || next != 11 {
		t.Fatalf("new lines = %#v, next = %d", lines, next)
	}
	file, err = os.OpenFile(path, os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := file.WriteString(" line\n"); err != nil {
		t.Fatal(err)
	}
	if err := file.Close(); err != nil {
		t.Fatal(err)
	}
	lines, next = tailer.Poll()
	if len(lines) != 1 || lines[0].Seq != 11 || lines[0].Line != "partial line" || next != 12 {
		t.Fatalf("partial lines = %#v, next = %d", lines, next)
	}
	if err := os.WriteFile(path, []byte("new\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	lines, next = tailer.Poll()
	if len(lines) != 1 || lines[0].Seq != 12 || lines[0].Line != "new" || next != 13 {
		t.Fatalf("truncated lines = %#v, next = %d", lines, next)
	}
}

// A deleted log file must reset the buffered fragment as well as the offset. Keeping the fragment
// meant that when the log came back, the old unterminated text was glued onto the front of the new
// file's first line and reported as one corrupted line.
func TestTailLogDropsThePartialLineWhenTheFileDisappears(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "macro_log.txt")
	if err := os.WriteFile(path, []byte(""), 0o600); err != nil {
		t.Fatal(err)
	}
	tailer := New(dir).TailLog(1)
	tailer.Poll() // initialize at the current end of file

	if err := os.WriteFile(path, []byte("an unterminated fragment"), 0o600); err != nil {
		t.Fatal(err)
	}
	if lines, _ := tailer.Poll(); len(lines) != 0 {
		t.Fatalf("an unterminated line must not be emitted yet, got %#v", lines)
	}

	if err := os.Remove(path); err != nil {
		t.Fatal(err)
	}
	tailer.Poll()

	if err := os.WriteFile(path, []byte("first line of the new log\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	lines, _ := tailer.Poll()
	if len(lines) != 1 || lines[0].Line != "first line of the new log" {
		t.Fatalf("lines = %#v, want the new first line alone", lines)
	}
}

func TestWaitForAckMatchesAndConsumes(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "remote_ack.txt")
	if err := os.WriteFile(path, []byte("token-1|ok|done\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	ack, err := New(dir).WaitForAck("token-1", time.Second)
	if err != nil || !ack.OK || ack.Message != "done" {
		t.Fatalf("ack = %#v, err = %v", ack, err)
	}
	if _, err := os.Stat(path); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("ack file was not consumed: %v", err)
	}
}
