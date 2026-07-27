// Package config manages the agent's local configuration and persistent state.
package config

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
)

// Config is the persistent configuration needed to connect an agent to a backend.
// DeviceToken is a bearer secret and must never be logged.
type Config struct {
	ServerURL   string `json:"serverURL"`
	DeviceToken string `json:"deviceToken"`
	DeviceID    string `json:"deviceId"`
	DeviceName  string `json:"deviceName"`
	MacroDir    string `json:"macroDir"`
}

// State holds small, durable runtime state that is not part of configuration.
// LogSeq is the next sequence number to assign to a newly tailed log line.
type State struct {
	LogSeq int64 `json:"logSeq"`
}

// DefaultPath returns the per-user default configuration file path.
func DefaultPath() (string, error) {
	dir, err := os.UserConfigDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, "AnimeExpeditionAgent", "config.json"), nil
}

// DefaultMacroDir returns the installed macro's per-user data directory. On
// Windows, os.UserCacheDir is %LocalAppData%, matching the AutoHotkey app.
func DefaultMacroDir() (string, error) {
	dir, err := os.UserCacheDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, "Anime Expedition Macro"), nil
}

// StatePath returns the state file kept beside a configuration file.
func StatePath(configPath string) string {
	return filepath.Join(filepath.Dir(configPath), "agent_state.json")
}

// Load reads a configuration JSON file from path.
func Load(path string) (*Config, error) {
	var cfg Config
	if err := loadJSON(path, &cfg); err != nil {
		return nil, err
	}
	return &cfg, nil
}

// Save atomically writes cfg to path with owner-only file permissions where supported.
func Save(path string, cfg *Config) error {
	if cfg == nil {
		return errors.New("config is nil")
	}
	return saveJSON(path, cfg)
}

// LoadState reads the durable state file beside the configuration file.
func LoadState(configPath string) (*State, error) {
	var state State
	if err := loadJSON(StatePath(configPath), &state); err != nil {
		return nil, err
	}
	return &state, nil
}

// SaveState atomically writes state beside the configuration file.
func SaveState(configPath string, state *State) error {
	if state == nil {
		return errors.New("state is nil")
	}
	return saveJSON(StatePath(configPath), state)
}

func loadJSON(path string, dst any) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(data, dst)
}

func saveJSON(path string, value any) error {
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')

	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return err
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, data, 0o600); err != nil {
		return err
	}
	if err := os.Chmod(tmp, 0o600); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	if err := os.Rename(tmp, path); err == nil {
		return nil
	}

	// Windows cannot rename over an existing file. Removing it is the closest
	// available replacement operation and the temporary file remains in the same
	// directory, so it never crosses a filesystem boundary.
	if err := os.Remove(path); err != nil && !errors.Is(err, os.ErrNotExist) {
		_ = os.Remove(tmp)
		return err
	}
	if err := os.Rename(tmp, path); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	return os.Chmod(path, 0o600)
}
