package adapter

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/iew-org/iew/internal/config"
)

func TestOllamaAdapter(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req map[string]any
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, err.Error(), 400)
			return
		}

		if req["model"] != "test-model" {
			t.Errorf("expected model test-model, got %v", req["model"])
		}

		resp := map[string]any{
			"response": "1: test finding\n",
			"thinking": "thought process",
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer ts.Close()

	cfg := config.DefaultConfig()
	cfg.Endpoint = ts.URL
	cfg.Model = "test-model"
	cfg.Request["model"] = "test-model"

	adp := NewOllamaAdapter(cfg)
	res, err := adp.Complete("test prompt")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if res != "1: test finding\n" {
		t.Errorf("unexpected response: %q", res)
	}
}

func TestOpenRouterAdapter(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		auth := r.Header.Get("Authorization")
		if auth != "Bearer secret-key" {
			http.Error(w, "Unauthorized", 401)
			return
		}

		var req map[string]any
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, err.Error(), 400)
			return
		}

		resp := map[string]any{
			"choices": []map[string]any{
				{
					"message": map[string]any{
						"content": "5: unused param",
					},
				},
			},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer ts.Close()

	cfg := config.DefaultConfig()
	cfg.Provider = "openrouter"
	cfg.Endpoint = ts.URL
	cfg.APIKey = "secret-key"

	adp := NewOpenRouterAdapter(cfg)
	res, err := adp.Complete("test prompt")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if res != "5: unused param" {
		t.Errorf("unexpected response: %q", res)
	}
}
