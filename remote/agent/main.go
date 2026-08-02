// Command agent bridges Kimberlite's Macro Menu to the remote backend.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"log"
	"os"
	"runtime"
	"strings"

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
	loginFlag := flags.Bool("login", false, "sign in to an existing remote-control account and pair this device")
	registerFlag := flags.Bool("register", false, "create a new remote-control account and pair this device")
	email := flags.String("email", "", "account email (used with --login/--register)")
	credentialsFile := flags.String("credentials-file", "", "file containing the account password on line 1 and an optional TOTP code on line 2 (used with --login/--register; read once, then deleted)")
	authResultFile := flags.String("auth-result-file", "", "write the --login/--register outcome as one line of text to this file (for GUI integrations that don't read stdout)")
	macroDir := flags.String("macro-dir", "", "macro bridge data directory")
	deviceName := flags.String("device-name", "", "local device name override")
	pollWait := flags.Int("poll-wait", 25, "command long-poll wait in seconds")
	showVersion := flags.Bool("version", false, "print version and exit")
	showStatus := flags.Bool("status", false, "print macro status and exit")
	if err := flags.Parse(args); err != nil {
		return err
	}
	// Registered as early as possible (right after parsing, before any other flag validation) so a
	// supplied --credentials-file is cleaned up no matter which later check causes this function to
	// return - not just the ones inside doAuthenticate - since the file holds a plaintext password.
	if *credentialsFile != "" {
		credFilePath := *credentialsFile
		defer func() {
			if err := os.Remove(credFilePath); err != nil && !errors.Is(err, os.ErrNotExist) {
				log.Printf("warning: could not delete credentials file %s: %v", credFilePath, err)
			}
		}()
	}
	if *showVersion {
		fmt.Println(Version)
		return nil
	}
	if *pollWait < 0 {
		return errors.New("--poll-wait cannot be negative")
	}
	if *loginFlag && *registerFlag {
		return errors.New("--login and --register cannot both be set")
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

	if *loginFlag || *registerFlag {
		mode := protocol.AgentAuthLogin
		if *registerFlag {
			mode = protocol.AgentAuthRegister
		}
		return authenticate(*configPath, cfg, mode, *email, *credentialsFile, *authResultFile)
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
		return errors.New("agent is not paired; run with --login (or --register), --email, --credentials-file and --server first")
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

// maxResultMessageLen bounds how much of an error is copied into the result file. doAuthenticate's
// error can wrap the configured backend's raw (if non-2xx) response body - the server URL is user-
// supplied, so this keeps a misbehaving or malicious "backend" from dumping unbounded text into
// the macro's log/GUI rather than trusting its length.
const maxResultMessageLen = 500

// authenticate signs in to (or registers) the account and pairs this device using its credentials,
// replacing the old one-time pairing code. When resultFile is non-empty, the outcome (success, or a
// friendly error message - never the password or the device token itself, which only ever exists on
// the success path below, where the message is the fixed string) is also written there as one line
// of plain text, so a caller that only launches this process (e.g. the macro's GUI) can show a
// precise result without having to capture stdout/stderr through a shell. Writing that file is
// best-effort: its failure must never turn a successful pairing (the token is already saved by this
// point) into a reported failure, so it does not affect the returned error.
func authenticate(configPath string, cfg *config.Config, mode protocol.AgentAuthMode, email, credentialsFile, resultFile string) error {
	err := doAuthenticate(configPath, cfg, mode, email, credentialsFile)
	if resultFile != "" {
		message := "Pairing successful. The device token was saved securely."
		if err != nil {
			message = truncateMessage(friendlyAuthError(err), maxResultMessageLen)
		}
		_ = os.WriteFile(resultFile, []byte(message+"\n"), 0o600)
	}
	return err
}

// friendlyAuthError turns a backend error code (see remote/PROTOCOL.md section 3.2) into wording a
// human reading the GUI's result box can act on, falling back to the raw error for anything else
// (network failure, an unexpected backend response, ...).
func friendlyAuthError(err error) string {
	switch client.AgentAuthErrorCode(err) {
	case "totp_required":
		return "This account has two-factor authentication enabled. Enter the current code from your authenticator app in the 2FA field and try again."
	case "invalid_totp":
		return "That two-factor code was not accepted. Check your authenticator app and try again."
	case "invalid_credentials":
		return "Incorrect email or password."
	case "email_already_registered":
		return "An account with that email already exists. Use Login instead of Register."
	case "account_locked":
		return "Too many wrong codes. The account is temporarily locked - wait a while and try again."
	case "too_many_requests":
		return "Too many attempts in a short time. Wait a minute and try again."
	default:
		return "Pairing failed: " + err.Error()
	}
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

// readCredentials reads a password (line 1) and an optional TOTP code (line 2) from a small
// caller-supplied file, rather than accepting either on the command line. A password is sensitive
// for the account's whole lifetime (unlike a short-lived pairing code), and Windows lets other
// processes on the same machine enumerate a running process's command line, so it must never appear
// there. The password is returned exactly as read (no trimming - it may legitimately contain
// whitespace); the TOTP code is trimmed since it is always a short numeric string.
func readCredentials(path string) (password, totp string, err error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", "", err
	}
	lines := strings.SplitN(strings.ReplaceAll(string(data), "\r\n", "\n"), "\n", 2)
	password = lines[0]
	if len(lines) > 1 {
		totp = strings.TrimSpace(lines[1])
	}
	return password, totp, nil
}

// doAuthenticate assumes the caller (run) has already arranged for credentialsFile to be deleted
// when this whole invocation is done - that must be set up before any of run's OTHER flag
// validation, not just the checks below, so it stays unconditional here too.
func doAuthenticate(configPath string, cfg *config.Config, mode protocol.AgentAuthMode, email, credentialsFile string) error {
	if credentialsFile == "" {
		return errors.New("--credentials-file is required with --login/--register")
	}
	if cfg.ServerURL == "" {
		return errors.New("--server is required when no server URL has been saved")
	}
	if email == "" {
		return errors.New("--email is required with --login/--register")
	}
	password, totp, err := readCredentials(credentialsFile)
	if err != nil {
		return fmt.Errorf("read credentials file: %w", err)
	}
	if password == "" {
		return errors.New("credentials file did not contain a password")
	}

	hostname, err := os.Hostname()
	if err != nil {
		return fmt.Errorf("get hostname: %w", err)
	}
	api := client.New(cfg.ServerURL, "", "AnimeExpeditionAgent/"+Version)
	response, err := api.Auth(context.Background(), protocol.AgentAuthRequest{
		Mode:         mode,
		Email:        email,
		Password:     password,
		TOTP:         totp,
		DeviceName:   cfg.DeviceName,
		Hostname:     hostname,
		AgentVersion: Version,
		OS:           runtime.GOOS,
	})
	if err != nil {
		return fmt.Errorf("pair agent: %w", err)
	}
	cfg.DeviceToken = response.DeviceToken
	cfg.DeviceID = response.DeviceID
	// A supplied --device-name is sent as the request's requested name (so it also becomes the name
	// shown on the dashboard); otherwise adopt the backend's own default (hostname-based).
	if response.DeviceName != "" && cfg.DeviceName == "" {
		cfg.DeviceName = response.DeviceName
	}
	if err := config.Save(configPath, cfg); err != nil {
		return fmt.Errorf("save configuration: %w", err)
	}
	fmt.Println("Pairing successful. The device token was saved securely.")
	return nil
}
