package config

import (
	"os"
	"path/filepath"
	"strings"

	"github.com/pelletier/go-toml/v2"
)

// Config represents the application configuration.
type Config struct {
	Provider        string                 `toml:"provider"`
	Model           string                 `toml:"model"`
	OpenRouterModel string                 `toml:"openrouter_model"`
	APIKey          string                 `toml:"api_key"`
	Key             string                 `toml:"key"`
	OpenRouterKey   string                 `toml:"openrouter_key"`
	LogLevel        string                 `toml:"log_level"`
	LogFile         string                 `toml:"log_file"`
	Debounce        float64                `toml:"debounce"`
	Timeout         float64                `toml:"timeout"`
	MaxRetries      int                    `toml:"max_retries"`
	Endpoint        string                 `toml:"endpoint"`
	Prompt          string                 `toml:"prompt"`
	Thinking        any                    `toml:"thinking"`
	KeepAlive       string                 `toml:"keep_alive"`
	Request         map[string]any         `toml:"request"`
	Raw             map[string]any         `toml:"-"`
}

func DefaultConfig() *Config {
	return &Config{
		Provider:   "ollama",
		Model:      "llama3",
		LogLevel:   "INFO",
		LogFile:    "~/.config/iew/iew.log",
		Debounce:   15,
		Timeout:    180,
		MaxRetries: 3,
		Endpoint:   "http://localhost:11434/api/generate",
		Request: map[string]any{
			"model":      "llama3",
			"keep_alive": "30m",
		},
		Raw: make(map[string]any),
	}
}

// ExpandPath expands ~ to user's home directory.
func ExpandPath(path string) string {
	if strings.HasPrefix(path, "~/") || path == "~" {
		home, err := os.UserHomeDir()
		if err == nil {
			if path == "~" {
				return home
			}
			return filepath.Join(home, path[2:])
		}
	}
	return path
}

// GetConfig loads the configuration from path, IEW_CONFIG, or ~/.config/iew/iew.toml.
func GetConfig(configPath string) *Config {
	cfg := DefaultConfig()

	if configPath == "" {
		if env := os.Getenv("IEW_CONFIG"); env != "" {
			configPath = ExpandPath(env)
		} else {
			configPath = ExpandPath("~/.config/iew/iew.toml")
		}
	} else {
		configPath = ExpandPath(configPath)
	}

	data, err := os.ReadFile(configPath)
	if err != nil {
		return cfg
	}

	var raw map[string]any
	if err := toml.Unmarshal(data, &raw); err != nil {
		return cfg
	}
	cfg.Raw = raw

	var parsed Config
	if err := toml.Unmarshal(data, &parsed); err != nil {
		return cfg
	}

	if parsed.Provider != "" {
		cfg.Provider = parsed.Provider
	}
	if parsed.Model != "" {
		cfg.Model = parsed.Model
	}
	if parsed.OpenRouterModel != "" {
		cfg.OpenRouterModel = parsed.OpenRouterModel
	}
	if parsed.APIKey != "" {
		cfg.APIKey = parsed.APIKey
	}
	if parsed.Key != "" {
		cfg.Key = parsed.Key
	}
	if parsed.OpenRouterKey != "" {
		cfg.OpenRouterKey = parsed.OpenRouterKey
	}
	if parsed.LogLevel != "" {
		cfg.LogLevel = parsed.LogLevel
	}
	if parsed.LogFile != "" {
		cfg.LogFile = parsed.LogFile
	}
	if parsed.Debounce != 0 {
		cfg.Debounce = parsed.Debounce
	}
	if parsed.Timeout != 0 {
		cfg.Timeout = parsed.Timeout
	}
	if parsed.MaxRetries != 0 {
		cfg.MaxRetries = parsed.MaxRetries
	}
	if parsed.Endpoint != "" {
		cfg.Endpoint = parsed.Endpoint
	}

	providerLower := strings.ToLower(cfg.Provider)

	if _, ok := raw["endpoint"]; !ok {
		if providerLower == "openrouter" {
			cfg.Endpoint = "https://openrouter.ai/api/v1/chat/completions"
		} else {
			cfg.Endpoint = "http://localhost:11434/api/generate"
		}
	}

	if providerLower == "openrouter" {
		_, hasRootModel := raw["model"]
		hasReqModel := false
		if reqMap, ok := raw["request"].(map[string]any); ok {
			_, hasReqModel = reqMap["model"]
		}
		if !hasRootModel && !hasReqModel {
			defaultORModel := "deepseek/deepseek-chat-v3-0324:free"
			if cfg.OpenRouterModel != "" {
				defaultORModel = cfg.OpenRouterModel
			}
			cfg.Model = defaultORModel
			cfg.Request["model"] = defaultORModel
		}
	}

	if reqMap, ok := raw["request"].(map[string]any); ok {
		for k, v := range reqMap {
			cfg.Request[k] = v
		}
	}

	if _, ok := raw["model"]; ok {
		cfg.Request["model"] = raw["model"]
	}
	if _, ok := raw["prompt"]; ok {
		cfg.Request["prompt"] = raw["prompt"]
	}
	if _, ok := raw["thinking"]; ok {
		cfg.Request["thinking"] = raw["thinking"]
	}
	if _, ok := raw["keep_alive"]; ok {
		cfg.Request["keep_alive"] = raw["keep_alive"]
	}

	if m, ok := cfg.Request["model"].(string); ok && m != "" {
		cfg.Model = m
	}

	return cfg
}

func (c *Config) GetEffectivePrompt() string {
	if p, ok := c.Request["prompt"].(string); ok && p != "" {
		return p
	}
	return c.Prompt
}

func (c *Config) GetEffectiveAPIKey() string {
	if c.APIKey != "" {
		return c.APIKey
	}
	if c.Key != "" {
		return c.Key
	}
	if c.OpenRouterKey != "" {
		return c.OpenRouterKey
	}
	return os.Getenv("OPENROUTER_API_KEY")
}
