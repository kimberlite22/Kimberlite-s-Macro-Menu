// Package version compares dotted numeric agent version strings.
package version

import "strings"

// Compare compares dotted numeric version strings and returns -1, 0, or 1.
// Missing and non-numeric components are treated as zero.
func Compare(a, b string) int {
	aParts := strings.Split(a, ".")
	bParts := strings.Split(b, ".")
	length := len(aParts)
	if len(bParts) > length {
		length = len(bParts)
	}
	for i := 0; i < length; i++ {
		av := component(aParts, i)
		bv := component(bParts, i)
		if av < bv {
			return -1
		}
		if av > bv {
			return 1
		}
	}
	return 0
}

// IsNewer reports whether candidate is newer than current.
func IsNewer(candidate, current string) bool {
	return Compare(candidate, current) > 0
}

func component(parts []string, index int) int {
	if index >= len(parts) {
		return 0
	}
	// Clamp to avoid integer overflow from an absurdly long (possibly hostile) component. Real
	// version components are tiny, so clamping far above any realistic value keeps ordering correct.
	const maxValue = 1 << 30
	value := 0
	for _, character := range parts[index] {
		if character < '0' || character > '9' {
			return 0
		}
		value = value*10 + int(character-'0')
		if value >= maxValue {
			return maxValue
		}
	}
	return value
}
