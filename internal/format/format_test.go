package format

import (
	"testing"
)

func TestParseCoordinate(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		wantKind string
		wantLine int
		wantMsg  string
		wantNil  bool
	}{
		{
			name:     "standard line coordinate",
			input:    "12: Unused variable.",
			wantKind: "line",
			wantLine: 12,
			wantMsg:  "Unused variable.",
		},
		{
			name:     "prefix Line with space",
			input:    "Line 12: Unused variable.",
			wantKind: "line",
			wantLine: 12,
			wantMsg:  "Unused variable.",
		},
		{
			name:     "no space after colon",
			input:    "12:feedback",
			wantKind: "line",
			wantLine: 12,
			wantMsg:  "feedback",
		},
		{
			name:     "line with colon in message",
			input:    "15: Error: variable 'foo' is undefined: check line 2",
			wantKind: "line",
			wantLine: 15,
			wantMsg:  "Error: variable 'foo' is undefined: check line 2",
		},
		{
			name:    "empty string",
			input:   "",
			wantNil: true,
		},
		{
			name:    "garbage text",
			input:   "This is just normal text without coordinate format",
			wantNil: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ParseCoordinate(tt.input)
			if tt.wantNil {
				if got != nil {
					t.Fatalf("ParseCoordinate(%q) expected nil, got %+v", tt.input, got)
				}
				return
			}

			if got == nil {
				t.Fatalf("ParseCoordinate(%q) returned nil", tt.input)
			}
			if got.Kind != tt.wantKind || got.LineNum != tt.wantLine || got.Message != tt.wantMsg {
				t.Errorf("ParseCoordinate(%q) = (%q, %d, %q); want (%q, %d, %q)",
					tt.input, got.Kind, got.LineNum, got.Message, tt.wantKind, tt.wantLine, tt.wantMsg)
			}
		})
	}
}
