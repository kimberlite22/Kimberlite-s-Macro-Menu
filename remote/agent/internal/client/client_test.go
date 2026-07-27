package client

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/animeexpedition/agent/internal/protocol"
)

func TestPairPollAndReport(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case protocol.PathPair:
			if r.Method != http.MethodPost || r.Header.Get("Authorization") != "" || r.Header.Get("Content-Type") != "application/json" {
				t.Errorf("pair request = %s auth=%q content-type=%q", r.Method, r.Header.Get("Authorization"), r.Header.Get("Content-Type"))
			}
			body, _ := io.ReadAll(r.Body)
			var got protocol.PairRequest
			if err := json.Unmarshal(body, &got); err != nil || got.Code != "code" {
				t.Errorf("pair body = %s, %v", body, err)
			}
			_, _ = w.Write([]byte(`{"deviceToken":"secret","deviceId":"id","deviceName":"PC"}`))
		case protocol.PathCommands:
			if r.Method != http.MethodGet || r.URL.Query().Get("wait") != "7" || r.Header.Get("Authorization") != "Bearer token" {
				t.Errorf("commands request = %s wait=%q auth=%q", r.Method, r.URL.Query().Get("wait"), r.Header.Get("Authorization"))
			}
			_, _ = w.Write([]byte(`{"commands":[{"id":"1","type":"PAUSE","arg":""}]}`))
		case protocol.PathReport:
			if r.Method != http.MethodPost || r.Header.Get("Authorization") != "Bearer token" || r.Header.Get("Content-Type") != "application/json" {
				t.Errorf("report request = %s auth=%q content-type=%q", r.Method, r.Header.Get("Authorization"), r.Header.Get("Content-Type"))
			}
			body, _ := io.ReadAll(r.Body)
			var got protocol.ReportRequest
			if err := json.Unmarshal(body, &got); err != nil || len(got.Acks) != 1 || got.Acks[0].CommandID != "1" {
				t.Errorf("report body = %s, %v", body, err)
			}
			_, _ = w.Write([]byte(`{"ok":true}`))
		default:
			t.Errorf("unexpected path %s", r.URL.Path)
		}
	}))
	defer server.Close()

	ctx := context.Background()
	pairClient := New(server.URL, "", "test-agent")
	if _, err := pairClient.Pair(ctx, protocol.PairRequest{Code: "code"}); err != nil {
		t.Fatalf("Pair: %v", err)
	}
	authClient := New(server.URL, "token", "test-agent")
	commands, err := authClient.PollCommands(ctx, 7)
	if err != nil || len(commands) != 1 || commands[0].Type != protocol.CmdPause {
		t.Fatalf("PollCommands = %#v, %v", commands, err)
	}
	if _, err := authClient.Report(ctx, protocol.ReportRequest{Acks: []protocol.Ack{{CommandID: "1", OK: true}}}); err != nil {
		t.Fatalf("Report: %v", err)
	}
}

func TestUnauthorizedIsTyped(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte(`{"error":"revoked"}`))
	}))
	defer server.Close()
	_, err := New(server.URL, "token", "test-agent").PollCommands(context.Background(), 0)
	if !errors.Is(err, ErrUnauthorized) {
		t.Fatalf("error = %v; want ErrUnauthorized", err)
	}
}
