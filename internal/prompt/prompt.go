package prompt

import (
	"fmt"
	"strings"
)

const OutputFormatInstructions = `Output format instructions:
- Each finding MUST start with a line number and a colon and a space:
  <line>: <concise description of issue>
- Output ONLY the formatted issue lines (one per line). If no issues exist, leave response completely blank.

Examples of valid output:
12: Hardcoded credentials detected.
45: Unused variable 'unusedval'.`

// BuildPrompt creates a review prompt based on user config, filename, and numbered source code lines.
func BuildPrompt(customPrompt, displayName, numberedLines string) string {
	trimmedPrompt := strings.TrimSpace(customPrompt)

	standardFormat := "Output format instructions:\n" +
		"- Each finding MUST start with a line number and a colon and a space:\n" +
		"  <line>: <concise description of issue>\n" +
		"- Output ONLY the formatted issue lines (one per line). If no issues exist, leave response completely blank.\n\n" +
		"Examples of valid output:\n" +
		"12: Hardcoded credentials detected.\n" +
		"45: Unused variable 'unused_val'."

	if trimmedPrompt == "" {
		return fmt.Sprintf("Review the code and provide code review feedback for any issues, bugs, or improvements.\n\n%s\n\nCode file: %s\n\nCode with line numbers:\n%s",
			standardFormat,
			displayName,
			numberedLines,
		)
	}

	replacements := map[string]string{
		"{display_name}":   displayName,
		"{filename}":       displayName,
		"{file}":           displayName,
		"{numbered_lines}": numberedLines,
		"{code}":           numberedLines,
	}

	promptText := trimmedPrompt
	for k, v := range replacements {
		promptText = strings.ReplaceAll(promptText, k, v)
	}

	hasCode := strings.Contains(trimmedPrompt, "{numbered_lines}") || strings.Contains(trimmedPrompt, "{code}")
	if hasCode {
		if !strings.Contains(promptText, "<line>:") && !strings.Contains(promptText, "Output format") {
			promptText = fmt.Sprintf("%s\n\n%s", promptText, standardFormat)
		}
		return promptText
	}

	return fmt.Sprintf("%s\n\n%s\n\nCode file: %s\n\nCode with line numbers:\n%s",
		promptText,
		standardFormat,
		displayName,
		numberedLines,
	)
}
