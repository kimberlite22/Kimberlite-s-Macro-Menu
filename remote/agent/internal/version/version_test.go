package version

import "testing"

func TestCompare(t *testing.T) {
	tests := []struct {
		name string
		a    string
		b    string
		want int
	}{
		{name: "newer patch", a: "0.2.0", b: "0.1.9", want: 1},
		{name: "older minor", a: "1.4.0", b: "1.5.0", want: -1},
		{name: "missing components", a: "1.2", b: "1.2.0", want: 0},
		{name: "non-numeric component", a: "1.beta.1", b: "1.0.1", want: 0},
		{name: "empty component", a: "2..3", b: "2.0.3", want: 0},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if got := Compare(test.a, test.b); got != test.want {
				t.Fatalf("Compare(%q, %q) = %d, want %d", test.a, test.b, got, test.want)
			}
		})
	}
}

func TestIsNewer(t *testing.T) {
	if !IsNewer("1.0.1", "1.0.0") {
		t.Fatal("IsNewer() = false, want true")
	}
	if IsNewer("1.0.0", "1.0.0") {
		t.Fatal("IsNewer() = true, want false")
	}
}
