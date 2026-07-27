package runner

import (
	"errors"
	"fmt"
	"strings"
	"testing"

	"github.com/animeexpedition/agent/internal/client"
)

func TestIsPermanentReportError(t *testing.T) {
	cases := []struct {
		name string
		err  error
		want bool
	}{
		{"nil", nil, false},
		{"network/timeout", errors.New("connection refused"), false},
		{"400 bad request", &client.HTTPError{StatusCode: 400}, true},
		{"413 payload too large", &client.HTTPError{StatusCode: 413}, true},
		{"429 rate limited (transient)", &client.HTTPError{StatusCode: 429}, false},
		{"500 server error (transient)", &client.HTTPError{StatusCode: 500}, false},
		{"503 unavailable (transient)", &client.HTTPError{StatusCode: 503}, false},
		{"wrapped 400", fmt.Errorf("report: %w", &client.HTTPError{StatusCode: 400}), true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := isPermanentReportError(tc.err); got != tc.want {
				t.Fatalf("isPermanentReportError(%v) = %v, want %v", tc.err, got, tc.want)
			}
		})
	}
}

func TestTruncateMessage(t *testing.T) {
	short := "Applied QUEUE_PRESET."
	if truncateMessage(short) != short {
		t.Fatalf("short message should be unchanged")
	}
	long := strings.Repeat("x", maxAckMessage+50)
	got := truncateMessage(long)
	if len([]rune(got)) != maxAckMessage {
		t.Fatalf("truncated length = %d, want %d", len([]rune(got)), maxAckMessage)
	}
	// Multi-byte runes must not be split.
	multi := strings.Repeat("ä", maxAckMessage+10)
	gotMulti := truncateMessage(multi)
	if len([]rune(gotMulti)) != maxAckMessage {
		t.Fatalf("multibyte truncated rune count = %d, want %d", len([]rune(gotMulti)), maxAckMessage)
	}
}
