package format

import (
	"regexp"
	"strconv"
	"strings"
)

var lineRegex = regexp.MustCompile(`(\d+):`)

// Coordinate represents a parsed issue coordinate from LLM feedback.
type Coordinate struct {
	Kind    string
	LineNum int
	Message string
}

// ParseCoordinate parses an iew-format coordinate line.
// Supported formats:
// - 12: Unused variable.
// - Line 12: Unused variable.
// - 12:feedback
// - Line 12:feedback
func ParseCoordinate(line string) *Coordinate {
	trimmed := strings.TrimSpace(line)
	if trimmed == "" {
		return nil
	}

	loc := lineRegex.FindStringSubmatchIndex(trimmed)
	if loc == nil {
		return nil
	}

	numStr := trimmed[loc[2]:loc[3]]
	lineNum, err := strconv.Atoi(numStr)
	if err != nil {
		return nil
	}

	text := strings.TrimSpace(trimmed[loc[1]:])
	return &Coordinate{
		Kind:    "line",
		LineNum: lineNum,
		Message: text,
	}
}
