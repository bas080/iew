package prompt

import (
	"strings"
	"testing"
)

func TestBuildPrompt_Default(t *testing.T) {
	prompt := BuildPrompt("", "main.go", "1:package main\n2:func main() {}")

	if !strings.Contains(prompt, "Review the code and provide code review feedback") {
		t.Errorf("expected default review message in prompt, got:\n%s", prompt)
	}
	if !strings.Contains(prompt, "Output format instructions:") {
		t.Errorf("expected output format instructions in prompt")
	}
	if !strings.Contains(prompt, "Code file: main.go") {
		t.Errorf("expected code file: main.go in prompt")
	}
	if !strings.Contains(prompt, "1:package main\n2:func main() {}") {
		t.Errorf("expected numbered lines in prompt")
	}
}

func TestBuildPrompt_CustomInstructionWithoutPlaceholders(t *testing.T) {
	custom := "Focus only on SQL injection vulnerabilities."
	prompt := BuildPrompt(custom, "db.go", "1:query := fmt.Sprintf(...)")

	if !strings.HasPrefix(prompt, custom) {
		t.Errorf("expected prompt to start with custom instruction, got:\n%s", prompt)
	}
	if !strings.Contains(prompt, "Output format instructions:") {
		t.Errorf("expected output format instructions appended")
	}
	if !strings.Contains(prompt, "Code file: db.go") {
		t.Errorf("expected code file in prompt")
	}
}

func TestBuildPrompt_CustomTemplateWithPlaceholders(t *testing.T) {
	custom := "Review {filename} for issues:\n{code}\nOutput format:\n<line>: <concise description>"
	prompt := BuildPrompt(custom, "app.py", "1:x = 1\n2:y = 2")

	expected := "Review app.py for issues:\n1:x = 1\n2:y = 2\nOutput format:\n<line>: <concise description>"
	if prompt != expected {
		t.Errorf("expected exact prompt match:\nGot:\n%s\nWant:\n%s", prompt, expected)
	}
}

func TestBuildPrompt_CustomTemplateWithCodePlaceholderMissingFormat(t *testing.T) {
	custom := "Analyze this file {filename}:\n{code}"
	prompt := BuildPrompt(custom, "app.py", "1:x = 1")

	if !strings.Contains(prompt, "Analyze this file app.py:\n1:x = 1") {
		t.Errorf("expected template substitution, got:\n%s", prompt)
	}
	if !strings.Contains(prompt, "Output format instructions:") {
		t.Errorf("expected Output format instructions appended when <line>: not present")
	}
}
