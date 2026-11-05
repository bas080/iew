package adapter

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"math"
	"net/http"
	"strings"
	"time"

	"github.com/iew-org/iew/internal/config"
)

// Adapter interface for model inference providers.
type Adapter interface {
	Name() string
	Complete(prompt string) (string, error)
}

// GetAdapter instantiates the appropriate adapter based on config.
func GetAdapter(cfg *config.Config) (Adapter, error) {
	provider := strings.ToLower(cfg.Provider)
	switch provider {
	case "ollama":
		return NewOllamaAdapter(cfg), nil
	case "openrouter":
		return NewOpenRouterAdapter(cfg), nil
	default:
		return nil, fmt.Errorf("unknown provider: %s", cfg.Provider)
	}
}

// OllamaAdapter communicates with Ollama's /api/generate endpoint.
type OllamaAdapter struct {
	config *config.Config
	client *http.Client
}

func NewOllamaAdapter(cfg *config.Config) *OllamaAdapter {
	timeout := time.Duration(cfg.Timeout) * time.Second
	if timeout <= 0 {
		timeout = 180 * time.Second
	}
	return &OllamaAdapter{
		config: cfg,
		client: &http.Client{Timeout: timeout},
	}
}

func (a *OllamaAdapter) Name() string {
	return "ollama"
}

func (a *OllamaAdapter) Complete(prompt string) (string, error) {
	payload := map[string]any{
		"model":  "llama3",
		"stream": false,
	}

	for k, v := range a.config.Request {
		if v != nil {
			payload[k] = v
		}
	}

	if _, ok := payload["model"]; !ok && a.config.Model != "" {
		payload["model"] = a.config.Model
	}

	if thinking, ok := payload["thinking"]; ok {
		delete(payload, "thinking")
		if _, exists := payload["think"]; !exists && thinking != nil {
			payload["think"] = thinking
		}
	}

	payload["prompt"] = prompt

	modelName, _ := payload["model"].(string)
	slog.Info("Using Ollama model", "model", modelName)

	endpoint := a.config.Endpoint
	if endpoint == "" {
		endpoint = "http://localhost:11434/api/generate"
	}
	slog.Info("Using Ollama endpoint", "endpoint", endpoint)

	bodyBytes, err := json.Marshal(payload)
	if err != nil {
		return "", fmt.Errorf("failed to encode request: %w", err)
	}

	maxRetries := a.config.MaxRetries
	if maxRetries <= 0 {
		maxRetries = 3
	}

	for attempt := 0; attempt < maxRetries; attempt++ {
		req, err := http.NewRequest("POST", endpoint, bytes.NewReader(bodyBytes))
		if err != nil {
			return "", fmt.Errorf("failed to create request: %w", err)
		}
		req.Header.Set("Content-Type", "application/json")

		resp, err := a.client.Do(req)
		if err != nil {
			slog.Error("Ollama request error", "err", err)
			if attempt == maxRetries-1 {
				return "", fmt.Errorf("Ollama request failed: %w", err)
			}
			time.Sleep(2 * time.Second)
			continue
		}

		respBody, err := io.ReadAll(resp.Body)
		resp.Body.Close()

		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			slog.Error("Ollama HTTP error", "status", resp.Status, "body", string(respBody))
			return "", fmt.Errorf("Ollama HTTP error: %s", resp.Status)
		}

		var data struct {
			Response string `json:"response"`
			Thinking string `json:"thinking"`
		}
		if err := json.Unmarshal(respBody, &data); err != nil {
			return "", fmt.Errorf("failed to parse Ollama response: %w", err)
		}

		if data.Thinking != "" {
			traceLen := min(500, len(data.Thinking))
			slog.Info("Ollama thinking trace", "trace", data.Thinking[:traceLen])
		}
		slog.Info("Ollama response received", "chars", len(data.Response))
		rawLen := min(500, len(data.Response))
		slog.Info("Ollama raw response", "preview", data.Response[:rawLen])

		return data.Response, nil
	}

	return "", nil
}

// OpenRouterAdapter communicates with OpenRouter's /api/v1/chat/completions endpoint.
type OpenRouterAdapter struct {
	config *config.Config
	client *http.Client
}

func NewOpenRouterAdapter(cfg *config.Config) *OpenRouterAdapter {
	timeout := time.Duration(cfg.Timeout) * time.Second
	if timeout <= 0 {
		timeout = 180 * time.Second
	}
	return &OpenRouterAdapter{
		config: cfg,
		client: &http.Client{Timeout: timeout},
	}
}

func (a *OpenRouterAdapter) Name() string {
	return "openrouter"
}

func (a *OpenRouterAdapter) Complete(prompt string) (string, error) {
	apiKey := a.config.GetEffectiveAPIKey()
	if apiKey == "" {
		slog.Error("API key missing: set api_key in config or OPENROUTER_API_KEY env")
		return "", fmt.Errorf("OpenRouter API key missing")
	}

	payload := map[string]any{
		"model":       "deepseek/deepseek-chat-v3-0324:free",
		"temperature": 0.0,
	}

	for k, v := range a.config.Request {
		if v != nil {
			payload[k] = v
		}
	}

	delete(payload, "api_key")
	delete(payload, "key")
	delete(payload, "openrouter_key")
	delete(payload, "prompt")

	if thinking, ok := payload["thinking"]; ok {
		delete(payload, "thinking")
		if _, exists := payload["reasoning"]; !exists && thinking != nil {
			switch t := thinking.(type) {
			case bool:
				if t {
					payload["reasoning"] = map[string]string{"effort": "medium"}
				} else {
					payload["reasoning"] = map[string]string{"effort": "none"}
				}
			case string:
				payload["reasoning"] = map[string]string{"effort": t}
			case float64:
				payload["reasoning"] = map[string]int{"max_tokens": int(t)}
			case int:
				payload["reasoning"] = map[string]int{"max_tokens": t}
			case map[string]any:
				payload["reasoning"] = t
			}
		}
	}

	if msgs, ok := payload["messages"].([]any); ok {
		payload["messages"] = append(msgs, map[string]string{"role": "user", "content": prompt})
	} else {
		payload["messages"] = []map[string]string{{"role": "user", "content": prompt}}
	}

	modelName, _ := payload["model"].(string)
	slog.Info("Using OpenRouter model", "model", modelName)

	endpoint := a.config.Endpoint
	if endpoint == "" {
		endpoint = "https://openrouter.ai/api/v1/chat/completions"
	}
	slog.Info("Using OpenRouter endpoint", "endpoint", endpoint)

	bodyBytes, err := json.Marshal(payload)
	if err != nil {
		return "", fmt.Errorf("failed to encode request: %w", err)
	}

	maxRetries := a.config.MaxRetries
	if maxRetries <= 0 {
		maxRetries = 3
	}

	backoff := 2.0
	for attempt := 0; attempt < maxRetries; attempt++ {
		req, err := http.NewRequest("POST", endpoint, bytes.NewReader(bodyBytes))
		if err != nil {
			return "", fmt.Errorf("failed to create request: %w", err)
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Authorization", "Bearer "+apiKey)

		resp, err := a.client.Do(req)
		if err != nil {
			slog.Error("OpenRouter request error", "err", err)
			if attempt == maxRetries-1 {
				return "", fmt.Errorf("OpenRouter request failed: %w", err)
			}
			time.Sleep(time.Duration(backoff) * time.Second)
			continue
		}

		respBody, err := io.ReadAll(resp.Body)
		resp.Body.Close()

		if resp.StatusCode == 429 && attempt < maxRetries-1 {
			wait := time.Duration(backoff*math.Pow(2, float64(attempt))) * time.Second
			slog.Warn("OpenRouter rate limit (429), retrying...", "wait", wait)
			time.Sleep(wait)
			continue
		}

		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			slog.Error("OpenRouter HTTP error", "status", resp.Status, "body", string(respBody))
			return "", fmt.Errorf("OpenRouter HTTP error: %s", resp.Status)
		}

		var data struct {
			Choices []struct {
				Message struct {
					Content          string `json:"content"`
					Reasoning        string `json:"reasoning"`
					ReasoningContent string `json:"reasoning_content"`
				} `json:"message"`
			} `json:"choices"`
			Response string `json:"response"`
		}

		if err := json.Unmarshal(respBody, &data); err != nil {
			return "", fmt.Errorf("failed to parse OpenRouter response: %w", err)
		}

		output := ""
		if len(data.Choices) > 0 {
			msg := data.Choices[0].Message
			reasoning := msg.Reasoning
			if reasoning == "" {
				reasoning = msg.ReasoningContent
			}
			if reasoning != "" {
				traceLen := min(500, len(reasoning))
				slog.Info("OpenRouter reasoning trace", "trace", reasoning[:traceLen])
			}
			output = msg.Content
		} else if data.Response != "" {
			output = data.Response
		}

		slog.Info("OpenRouter response received", "chars", len(output))
		rawLen := min(500, len(output))
		slog.Info("OpenRouter raw response", "preview", output[:rawLen])

		return output, nil
	}

	return "", nil
}
