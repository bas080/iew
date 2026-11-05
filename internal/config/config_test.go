package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestDefaultConfig(t *testing.T) {
	cfg := GetConfig("/nonexistent/path/to/iew.toml")
	if cfg.Provider != "ollama" {
		t.Errorf("expected default provider ollama, got %s", cfg.Provider)
	}
	if cfg.Model != "llama3" {
		t.Errorf("expected default model llama3, got %s", cfg.Model)
	}
	if cfg.Endpoint != "http://localhost:11434/api/generate" {
		t.Errorf("expected default endpoint http://localhost:11434/api/generate, got %s", cfg.Endpoint)
	}
	if cfg.Debounce != 15 {
		t.Errorf("expected default debounce 15, got %v", cfg.Debounce)
	}
	if cfg.Timeout != 180 {
		t.Errorf("expected default timeout 180, got %v", cfg.Timeout)
	}
}

func TestCustomTomlConfig(t *testing.T) {
	tempDir := t.TempDir()
	tomlPath := filepath.Join(tempDir, "iew.toml")

	tomlContent := `
provider = "openrouter"
debounce = 30
timeout = 60
api_key = "test-key-123"

[request]
model = "anthropic/claude-3-opus"
temperature = 0.5
`
	if err := os.WriteFile(tomlPath, []byte(tomlContent), 0644); err != nil {
		t.Fatalf("failed to write test toml: %v", err)
	}

	cfg := GetConfig(tomlPath)

	if cfg.Provider != "openrouter" {
		t.Errorf("expected provider openrouter, got %s", cfg.Provider)
	}
	if cfg.Model != "anthropic/claude-3-opus" {
		t.Errorf("expected model anthropic/claude-3-opus, got %s", cfg.Model)
	}
	if cfg.Debounce != 30 {
		t.Errorf("expected debounce 30, got %v", cfg.Debounce)
	}
	if cfg.Timeout != 60 {
		t.Errorf("expected timeout 60, got %v", cfg.Timeout)
	}
	if cfg.GetEffectiveAPIKey() != "test-key-123" {
		t.Errorf("expected api key test-key-123, got %s", cfg.GetEffectiveAPIKey())
	}
	if cfg.Endpoint != "https://openrouter.ai/api/v1/chat/completions" {
		t.Errorf("expected openrouter endpoint, got %s", cfg.Endpoint)
	}
}

func TestOpenRouterDefaultModelWhenOmitted(t *testing.T) {
	tempDir := t.TempDir()
	tomlPath := filepath.Join(tempDir, "iew.toml")

	tomlContent := `
provider = "openrouter"
api_key = "test-key"
`
	if err := os.WriteFile(tomlPath, []byte(tomlContent), 0644); err != nil {
		t.Fatalf("failed to write test toml: %v", err)
	}

	cfg := GetConfig(tomlPath)
	if cfg.Model != "deepseek/deepseek-chat-v3-0324:free" {
		t.Errorf("expected default openrouter model, got %s", cfg.Model)
	}
}
