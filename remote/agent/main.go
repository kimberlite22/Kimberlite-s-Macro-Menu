// Command agent bridges Kimberlite's Anime Expedition Macro to the remote backend.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"log"
	"os"
	"runtime"

	"github.com/animeexpedition/agent/internal/bridge"
	"github.com/animeexpedition/agent/internal/client"
	"github.com/animeexpedition/agent/internal/config"
	"github.com/animeexpedition/agent/internal/protocol"
	"github.com/animeexpedition/agent/internal/runner"
)

// Version is the current agent release version.
const Version = "0.1.0"

func main() {
	log.SetFlags(log.LstdFlags)
	if err := run(os.Args[1:]); err != nil {
		log.Printf("error: %v", err)
		os.Exit(1)
	}
}

func run(args []string) error {
	defaultConfig, err := config.DefaultPath()
	if err != nil {
		return fmt.Errorf("find default config path: %w", err)
	}
	flags := flag.NewFlagSet("animeexpedition-agent", flag.ContinueOnError)
	flags.SetOutput(os.Stderr)
	configPath := flags.String("config", defaultConfig, "configuration file path")
	serverURL := flags.String("server", "", "backend server URL")
	pairCode := flags.String("pair", "", "one-time pairing code")
	pairResultFile := flags.String("pair-result-file", "", "write the --pair outcome as one line of text to this file (for GUI integrations that don't read stdout)")
	macroDir := flags.String("macro-dir", "", "macro bridge data directory")
	deviceName := flags.String("device-name", "", "local device name override")
	pollWait := flags.Int("poll-wait", 25, "command long-poll wait in seconds")
	showVersion := flags.Bool("version", false, "print version and exit")
	showStatus := flags.Bool("status", false, "print macro status and exit")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if *showVersion {
		fmt.Println(Version)
		return nil
	}
	if *pollWait < 0 {
		return errors.New("--poll-wait cannot be negative")
	}

	cfg, err := loadConfig(*configPath)
	if err != nil {
		return fmt.Errorf("load configuration: %w", err)
	}
	if cfg.MacroDir == "" || config.IsLegacyDefaultMacroDir(cfg.MacroDir) {
		defaultMacroDir, err := config.DefaultMacroDir()
		if err != nil {
			return fmt.Errorf("find default macro directory: %w", err)
		}
		cfg.MacroDir = defaultMacroDir
	}
	if *serverURL != "" {
		cfg.ServerURL = *serverURL
	}
	if *macroDir != "" {
		cfg.MacroDir = *macroDir
	}
	if *deviceName != "" {
		cfg.DeviceName = *deviceName
	}

	if *pairCode != "" {
		return pair(*configPath, cfg, *pairCode, *pairResultFile)
	}
	if *showStatus {
		status, err := bridge.New(cfg.MacroDir).ReadStatus()
		if err != nil {
			return fmt.Errorf("read macro status: %w", err)
		}
		fmt.Printf("%+v\n", *status)
		return nil
	}
	if cfg.ServerURL == "" || cfg.DeviceToken == "" {
		return errors.New("agent is not paired; run with --pair <code> and --server <url> first")
	}
	return runner.Run(*configPath, cfg, *pollWait, Version)
}

func loadConfig(path string) (*config.Config, error) {
	cfg, err := config.Load(path)
	if errors.Is(err, os.ErrNotExist) {
		return &config.Config{}, nil
	}
	return cfg, err
}

// maxResultMessageLen bounds how much of an error is copied into the result file. doPair's error
// can wrap the configured backend's raw (if non-2xx) response body - the server URL is user-
// supplied, so this keeps a misbehaving or malicious "backend" from dumping unbounded text into
// the macro's log/GUI rather than trusting its length.
const maxResultMessageLen = 500

// pair redeems a one-time pairing code. When resultFile is non-empty, the outcome (success or the
// error text - never the device token itself, which only ever exists on the success path below,
// where the message is the fixed string) is also written there as one line of plain text, so a
// caller that only launches this process (e.g. the macro's GUI) can show a precise result without
// having to capture stdout/stderr through a shell. Writing that file is best-effort: its failure
// must never turn a successful pairing (the token is already saved by this point) into a reported
// failure, so it does not affect the returned error.
func pair(configPath string, cfg *config.Config, code string, resultFile string) error {
	err := doPair(configPath, cfg, code)
	if resultFile != "" {
		message := "Pairing successful. The device token was saved securely."
		if err != nil {
			message = truncateMessage("Pairing failed: "+err.Error(), maxResultMessageLen)
		}
		_ = os.WriteFile(resultFile, []byte(message+"\n"), 0o600)
	}
	return err
}

func truncateMessage(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	runes := []rune(s)
	if len(runes) <= maxLen {
		return s
	}
	return string(runes[:maxLen]) + "..."
}

func doPair(configPath string, cfg *config.Config, code string) error {
	if cfg.ServerURL == "" {
		return errors.New("--server is required when no server URL has been saved")
	}
	hostname, err := os.Hostname()
	if err != nil {
		return fmt.Errorf("get hostname: %w", err)
	}
	api := client.New(cfg.ServerURL, "", "AnimeExpeditionAgent/"+Version)
	response, err := api.Pair(context.Background(), protocol.PairRequest{
		Code: code, Hostname: hostname, AgentVersion: Version, OS: runtime.GOOS,
	})
	if err != nil {
		return fmt.Errorf("pair agent: %w", err)
	}
	cfg.DeviceToken = response.DeviceToken
	cfg.DeviceID = response.DeviceID
	// The protocol does not carry a requested name during pairing. A supplied
	// --device-name is therefore a local override; otherwise use the backend's
	// name generated with the pairing code.
	if response.DeviceName != "" && cfg.DeviceName == "" {
		cfg.DeviceName = response.DeviceName
	}
	if err := config.Save(configPath, cfg); err != nil {
		return fmt.Errorf("save configuration: %w", err)
	}
	fmt.Println("Pairing successful. The device token was saved securely.")
	return nil
}
