// Package client contains the agent's outbound HTTPS client for the backend API.
package client

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/animeexpedition/agent/internal/protocol"
)

// ErrUnauthorized is returned when a device token has been rejected or revoked.
var ErrUnauthorized = errors.New("agent is unauthorized")

// HTTPError describes a non-successful backend response.
type HTTPError struct {
	StatusCode int
	Message    string
}

// Error implements error.
func (e *HTTPError) Error() string {
	if e.Message == "" {
		return fmt.Sprintf("backend returned HTTP %d", e.StatusCode)
	}
	return fmt.Sprintf("backend returned HTTP %d: %s", e.StatusCode, e.Message)
}

// AgentAuthErrorCode extracts the backend's machine-readable error code (e.g. "totp_required",
// "invalid_credentials", "email_already_registered" - see PROTOCOL.md section 3.2) from an error
// returned by Auth, or "" if err does not carry one - a network failure, or an HTTPError whose body
// is not the expected `{"error":"..."}` shape.
func AgentAuthErrorCode(err error) string {
	var httpErr *HTTPError
	if !errors.As(err, &httpErr) {
		return ""
	}
	var body struct {
		Error string `json:"error"`
	}
	if json.Unmarshal([]byte(httpErr.Message), &body) != nil {
		return ""
	}
	return body.Error
}

// Client performs authenticated, outbound requests to the backend.
type Client struct {
	serverURL   string
	deviceToken string
	userAgent   string
	httpClient  *http.Client
}

// New creates a client with reasonable default request timeouts.
func New(serverURL, deviceToken, userAgent string) *Client {
	return &Client{
		serverURL:   strings.TrimRight(serverURL, "/"),
		deviceToken: deviceToken,
		userAgent:   userAgent,
		httpClient:  &http.Client{Timeout: 35 * time.Second},
	}
}

// Auth signs in to (or registers) the account and pairs this device, returning its device token.
func (c *Client) Auth(ctx context.Context, request protocol.AgentAuthRequest) (protocol.AgentAuthResponse, error) {
	var response protocol.AgentAuthResponse
	err := c.doJSON(ctx, http.MethodPost, protocol.PathAgentAuth, nil, request, &response, 35*time.Second)
	return response, err
}

// PollCommands long-polls for commands using the device bearer token.
func (c *Client) PollCommands(ctx context.Context, waitSeconds int) ([]protocol.Command, error) {
	if waitSeconds < 0 {
		return nil, errors.New("wait seconds cannot be negative")
	}
	path := protocol.PathCommands + "?wait=" + url.QueryEscape(strconv.Itoa(waitSeconds))
	var response protocol.CommandsResponse
	timeout := time.Duration(waitSeconds+10) * time.Second
	err := c.doJSON(ctx, http.MethodGet, path, &c.deviceToken, nil, &response, timeout)
	return response.Commands, err
}

// Report sends status, log lines, and command acknowledgements to the backend.
func (c *Client) Report(ctx context.Context, request protocol.ReportRequest) (protocol.ReportResponse, error) {
	var response protocol.ReportResponse
	err := c.doJSON(ctx, http.MethodPost, protocol.PathReport, &c.deviceToken, request, &response, 35*time.Second)
	return response, err
}

// GetVersion returns the agent versions advertised by the backend.
func (c *Client) GetVersion(ctx context.Context) (protocol.VersionResponse, error) {
	var response protocol.VersionResponse
	err := c.doJSON(ctx, http.MethodGet, protocol.PathVersion, nil, nil, &response, 10*time.Second)
	return response, err
}

func (c *Client) doJSON(ctx context.Context, method, path string, token *string, body, output any, timeout time.Duration) error {
	endpoint, err := c.endpoint(path)
	if err != nil {
		return err
	}
	var reader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return err
		}
		reader = bytes.NewReader(data)
	}
	req, err := http.NewRequestWithContext(ctx, method, endpoint, reader)
	if err != nil {
		return err
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if c.userAgent != "" {
		req.Header.Set("User-Agent", c.userAgent)
	}
	if token != nil {
		req.Header.Set("Authorization", "Bearer "+*token)
	}

	// Copying the client gives each long poll its own timeout without mutating
	// shared state while reporter and command goroutines run concurrently.
	hc := *c.httpClient
	hc.Timeout = timeout
	resp, err := hc.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		message, _ := io.ReadAll(io.LimitReader(resp.Body, 8<<10))
		httpErr := &HTTPError{StatusCode: resp.StatusCode, Message: strings.TrimSpace(string(message))}
		if resp.StatusCode == http.StatusUnauthorized {
			// Wrap both: errors.Is(_, ErrUnauthorized) keeps working for the token-rejected case, and
			// errors.As(_, &httpErr) also finds the HTTPError (see AgentAuthErrorCode), which a 401 for
			// agent auth (invalid_credentials / totp_required / invalid_totp) needs.
			return fmt.Errorf("%w: %w", ErrUnauthorized, httpErr)
		}
		return httpErr
	}
	if output == nil {
		return nil
	}
	return json.NewDecoder(resp.Body).Decode(output)
}

func (c *Client) endpoint(path string) (string, error) {
	base, err := url.Parse(c.serverURL)
	if err != nil {
		return "", err
	}
	if base.Scheme == "" || base.Host == "" {
		return "", errors.New("server URL must be an absolute URL")
	}
	rel, err := url.Parse(path)
	if err != nil {
		return "", err
	}
	return base.ResolveReference(rel).String(), nil
}
