package agent

import (
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strings"

	"github.com/iew-org/iew/internal/adapter"
	"github.com/iew-org/iew/internal/config"
	"github.com/iew-org/iew/internal/format"
	"github.com/iew-org/iew/internal/prompt"
)

// Agent manages configuration, prompt construction, LLM adapter invocation, and feedback parsing.
type Agent struct {
	Config *config.Config
}

func NewAgent(cfg *config.Config) *Agent {
	return &Agent{Config: cfg}
}

// ReviewContent reviews in-memory file content and returns feedback text.
func (a *Agent) ReviewContent(filename, content string) (string, error) {
	lines := strings.Split(content, "\n")
	slog.Info("Scanning lines for issues", "count", len(lines))

	displayName := filepath.Base(filename)
	numberedLines := make([]string, len(lines))
	for i, l := range lines {
		numberedLines[i] = fmt.Sprintf("%d:%s", i+1, l)
	}
	numberedText := strings.Join(numberedLines, "\n")

	customPrompt := a.Config.GetEffectivePrompt()
	systemPrompt := prompt.BuildPrompt(customPrompt, displayName, numberedText)

	adp, err := adapter.GetAdapter(a.Config)
	if err != nil {
		slog.Error("Failed to get adapter", "err", err)
		return "", err
	}

	output, err := adp.Complete(systemPrompt)
	if err != nil {
		slog.Error("Review error", "err", err)
		return fmt.Sprintf("error: %s", err), err
	}

	feedback := a.ProcessFeedback(output)
	slog.Info("Total feedback lines", "count", len(feedback))
	return strings.Join(feedback, "\n"), nil
}

// ReviewFile reads a file from disk and reviews its content.
func (a *Agent) ReviewFile(filePath, originalPath string) (string, error) {
	slog.Info("Reviewing file", "path", filePath)
	content, err := os.ReadFile(filePath)
	if err != nil {
		slog.Error("Read error", "err", err)
		return fmt.Sprintf("error: %s", err), err
	}

	targetName := originalPath
	if targetName == "" {
		targetName = filePath
	}

	return a.ReviewContent(targetName, string(content))
}

// ProcessFeedback filters raw LLM output into structured feedback lines.
func (a *Agent) ProcessFeedback(output string) []string {
	var feedback []string
	seen := make(map[string]bool)

	for _, rawLine := range strings.Split(output, "\n") {
		line := strings.TrimSpace(rawLine)
		line = strings.Trim(line, "\"'`")
		if strings.HasPrefix(line, "- ") || strings.HasPrefix(line, "* ") {
			line = strings.TrimSpace(line[2:])
			line = strings.Trim(line, "\"'`")
		}
		if line == "" {
			continue
		}

		coord := format.ParseCoordinate(line)
		if coord != nil {
			if !seen[line] {
				seen[line] = true
				feedback = append(feedback, line)
				slog.Info("Added AI feedback", "line", line)
			}
		} else if len(feedback) > 0 {
			feedback[len(feedback)-1] = fmt.Sprintf("%s\n%s", feedback[len(feedback)-1], line)
			slog.Info("Appended multi-line feedback", "line", line)
		}
	}

	return feedback
}
