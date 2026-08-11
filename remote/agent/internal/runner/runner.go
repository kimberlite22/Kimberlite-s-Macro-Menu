// Package runner contains the agent's concurrent reporting and command loops.
package runner

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"github.com/animeexpedition/agent/internal/bridge"
	"github.com/animeexpedition/agent/internal/client"
	"github.com/animeexpedition/agent/internal/config"
	"github.com/animeexpedition/agent/internal/protocol"
	"github.com/animeexpedition/agent/internal/version"
)

// Run starts reporting and command polling until a termination signal or a
// non-recoverable authorization error is received.
func Run(configPath string, cfg *config.Config, pollWait int, agentVersion string) error {
	state, err := config.LoadState(configPath)
	if errors.Is(err, os.ErrNotExist) {
		state = &config.State{}
	} else if err != nil {
		return fmt.Errorf("load agent state: %w", err)
	}

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	api := client.New(cfg.ServerURL, cfg.DeviceToken, "AnimeExpeditionAgent/"+agentVersion)
	fileBridge := bridge.New(cfg.MacroDir)
	versionNotifier := newVersionNotifier(agentVersion)
	// Best-effort and asynchronous: a slow or unreachable backend must never delay reporting or
	// command polling from starting.
	go checkStartupVersion(ctx, api, versionNotifier)
	var group sync.WaitGroup
	errs := make(chan error, 2)
	group.Add(2)
	go func() {
		defer group.Done()
		errs <- reporterLoop(ctx, api, fileBridge, configPath, state, versionNotifier)
	}()
	go func() {
		defer group.Done()
		errs <- commandLoop(ctx, api, fileBridge, pollWait, versionNotifier)
	}()

	var firstErr error
	select {
	case firstErr = <-errs:
		cancel()
	case <-ctx.Done():
	}
	group.Wait()
	if errors.Is(firstErr, client.ErrUnauthorized) {
		return errors.New("device token was rejected; run --login (or --register) again")
	}
	if firstErr != nil && !errors.Is(firstErr, context.Canceled) {
		return firstErr
	}
	return nil
}

const (
	// maxLogBatch keeps each report's log array well under the backend's per-request cap (1000) and
	// Postgres parameter limits, so a burst of macro logs is delivered in bounded chunks.
	maxLogBatch = 500
	// maxLogBuffer bounds the buffered-but-unsent log lines so a long backend outage cannot grow
	// memory without limit; the oldest lines are dropped past this (logs are best-effort).
	maxLogBuffer = 20000
)

func reporterLoop(ctx context.Context, api *client.Client, fileBridge *bridge.Bridge, configPath string, state *config.State, versionNotifier *versionNotifier) error {
	tailer := fileBridge.TailLog(state.LogSeq)
	var pending []protocol.LogLine
	backoff := time.Second
	// After a with-logs report is permanently rejected we probe with STATUS ONLY, to learn whether
	// the log batch is actually the cause before dropping any log data.
	probeStatusOnly := false
	for {
		status, statusErr := fileBridge.ReadStatus()
		if statusErr != nil {
			log.Printf("warning: read macro status: %v", statusErr)
			status = nil
		}
		logs, nextSeq := tailer.Poll()
		pending = append(pending, logs...)
		// Persist the monotonic tailer counter regardless of send success: it keeps the per-device
		// seq increasing across restarts and is NOT a delivery cursor.
		if state.LogSeq != nextSeq {
			state.LogSeq = nextSeq
			if err := config.SaveState(configPath, state); err != nil {
				log.Printf("warning: save agent state: %v", err)
			}
		}
		if len(pending) > maxLogBuffer {
			dropped := len(pending) - maxLogBuffer
			pending = pending[dropped:]
			log.Printf("warning: log buffer exceeded %d; dropping %d oldest line(s)", maxLogBuffer, dropped)
		}

		batchLen := 0
		if !probeStatusOnly {
			batchLen = len(pending)
			if batchLen > maxLogBatch {
				batchLen = maxLogBatch
			}
		}
		batch := pending[:batchLen]

		response, err := api.Report(ctx, protocol.ReportRequest{Status: status, Logs: batch})
		if err != nil {
			if errors.Is(err, client.ErrUnauthorized) {
				return err
			}
			if ctx.Err() != nil {
				return ctx.Err()
			}
			// ALWAYS back off before retrying so no failure path can become a tight busy-loop.
			if isPermanentReportError(err) {
				if len(batch) > 0 {
					// The request carrying logs was rejected. Do not assume the logs are at fault (it
					// could be the status or a request-level 4xx such as a wrong URL): probe next with
					// status only to find out, and only then decide whether to drop the log batch.
					log.Printf("warning: report with %d log line(s) rejected (%v); will retry status-only", len(batch), err)
					probeStatusOnly = true
				} else {
					// A status-only (or empty) request was rejected, so the logs are NOT the cause
					// (bad status or an unrecoverable request-level error). Keep the logs buffered and
					// keep retrying with capped backoff; this recovers if/when the backend is fixed.
					log.Printf("warning: report rejected without logs (%v); backing off", err)
				}
			} else {
				log.Printf("warning: report failed; retrying in %s: %v", backoff, err)
			}
			if !wait(ctx, backoff) {
				return ctx.Err()
			}
			backoff = growBackoff(backoff)
			continue
		}

		versionNotifier.warnIfNewer(response.LatestAgentVersion)
		backoff = time.Second
		if probeStatusOnly {
			// Status-only succeeded, so the previously attempted log batch is the poison. Drop that
			// head chunk (bounded, best-effort) to make progress, then resume sending logs.
			dropLen := len(pending)
			if dropLen > maxLogBatch {
				dropLen = maxLogBatch
			}
			if dropLen > 0 {
				log.Printf("warning: dropping %d log line(s) the backend rejected", dropLen)
				pending = pending[dropLen:]
			}
			probeStatusOnly = false
		} else {
			pending = pending[batchLen:]
		}

		// Drain any remaining buffered lines promptly instead of waiting a full second between chunks.
		pause := time.Second
		if len(pending) > 0 {
			pause = 50 * time.Millisecond
		}
		if !wait(ctx, pause) {
			return ctx.Err()
		}
	}
}

// isPermanentReportError reports whether a failed request will keep failing if retried unchanged:
// the backend rejected the request itself with a 4xx other than 429 (rate limiting) and 408
// (request timeout). Network errors, timeouts, 5xx, 429 and 408 are transient (false) and should be
// retried with backoff.
func isPermanentReportError(err error) bool {
	var httpErr *client.HTTPError
	if !errors.As(err, &httpErr) {
		return false
	}
	// 429 (rate limited) and 408 (request timeout) are the two 4xx codes that describe WHEN the
	// request arrived rather than what was in it, so an identical retry can succeed. Treating 408
	// as permanent was actively harmful: the caller reads a permanent failure on a request that
	// carried logs as proof the logs are poison, and then drops that whole batch (see the
	// probeStatusOnly path above), so a single slow request silently lost log lines.
	if httpErr.StatusCode == http.StatusTooManyRequests || httpErr.StatusCode == http.StatusRequestTimeout {
		return false
	}
	return httpErr.StatusCode >= 400 && httpErr.StatusCode < 500
}

func commandLoop(ctx context.Context, api *client.Client, fileBridge *bridge.Bridge, pollWait int, versionNotifier *versionNotifier) error {
	backoff := time.Second
	for {
		commands, err := api.PollCommands(ctx, pollWait)
		if err != nil {
			if errors.Is(err, client.ErrUnauthorized) {
				return err
			}
			if ctx.Err() != nil {
				return ctx.Err()
			}
			log.Printf("warning: command poll failed; retrying in %s: %v", backoff, err)
			if !wait(ctx, backoff) {
				return ctx.Err()
			}
			backoff = growBackoff(backoff)
			continue
		}
		backoff = time.Second
		for _, command := range commands {
			if err := reportAck(ctx, api, applyCommand(fileBridge, command), versionNotifier); err != nil {
				return err
			}
		}
	}
}

// maxAckMessage bounds the acknowledgement message the agent forwards, staying under the backend's
// cap so a very long macro-written ack line can never make the ack report fail validation.
const maxAckMessage = 500

func truncateMessage(message string) string {
	runes := []rune(message)
	if len(runes) <= maxAckMessage {
		return message
	}
	return string(runes[:maxAckMessage])
}

func applyCommand(fileBridge *bridge.Bridge, command protocol.Command) protocol.Ack {
	if err := fileBridge.SendCommand(command); err != nil {
		return protocol.Ack{CommandID: command.ID, Message: truncateMessage(err.Error())}
	}
	ack, err := fileBridge.WaitForAck(command.ID, 5*time.Second)
	if err != nil && !errors.Is(err, bridge.ErrAckTimeout) {
		return protocol.Ack{CommandID: command.ID, Message: truncateMessage(err.Error())}
	}
	ack.Message = truncateMessage(ack.Message)
	return ack
}

func reportAck(ctx context.Context, api *client.Client, ack protocol.Ack, versionNotifier *versionNotifier) error {
	backoff := time.Second
	for {
		response, err := api.Report(ctx, protocol.ReportRequest{Acks: []protocol.Ack{ack}})
		if err == nil {
			versionNotifier.warnIfNewer(response.LatestAgentVersion)
			return nil
		}
		if errors.Is(err, client.ErrUnauthorized) || ctx.Err() != nil {
			return err
		}
		// A permanently rejected ack (4xx other than 429) would otherwise loop forever and stall the
		// command loop; give up on this ack instead. The command was already applied via the bridge.
		if isPermanentReportError(err) {
			log.Printf("warning: backend rejected an acknowledgement (%v); dropping it", err)
			return nil
		}
		log.Printf("warning: acknowledgement report failed; retrying in %s: %v", backoff, err)
		if !wait(ctx, backoff) {
			return ctx.Err()
		}
		backoff = growBackoff(backoff)
	}
}

type versionNotifier struct {
	currentVersion    string
	lastWarnedVersion string
	mu                sync.Mutex
}

func newVersionNotifier(currentVersion string) *versionNotifier {
	return &versionNotifier{currentVersion: currentVersion}
}

func checkStartupVersion(ctx context.Context, api *client.Client, versionNotifier *versionNotifier) {
	response, err := api.GetVersion(ctx)
	if err != nil {
		log.Printf("debug: version check failed: %v", err)
		return
	}
	log.Printf("agent version: %s (latest %s)", versionNotifier.currentVersion, response.Latest)
	versionNotifier.warnIfNewer(response.Latest)
}

func (n *versionNotifier) warnIfNewer(latest string) {
	if !version.IsNewer(latest, n.currentVersion) {
		return
	}
	n.mu.Lock()
	defer n.mu.Unlock()
	if n.lastWarnedVersion == latest {
		return
	}
	n.lastWarnedVersion = latest
	log.Printf("WARNING: a newer agent version is available: %s (current %s); see the docs to update", latest, n.currentVersion)
}

func growBackoff(current time.Duration) time.Duration {
	if current >= 30*time.Second {
		return 30 * time.Second
	}
	current *= 2
	if current > 30*time.Second {
		return 30 * time.Second
	}
	return current
}

func wait(ctx context.Context, duration time.Duration) bool {
	timer := time.NewTimer(duration)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-timer.C:
		return true
	}
}
