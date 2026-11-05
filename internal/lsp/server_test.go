package lsp

import (
	"bytes"
	"encoding/json"
	"io"
	"strings"
	"testing"

	"github.com/iew-org/iew/internal/config"
)

func TestLSPServerInitializeAndShutdown(t *testing.T) {
	initReq := map[string]any{
		"jsonrpc": "2.0",
		"id":      1,
		"method":  "initialize",
		"params": map[string]any{
			"rootUri": "file:///workspace",
		},
	}
	initBytes, _ := EncodePayload(initReq)

	shutdownReq := map[string]any{
		"jsonrpc": "2.0",
		"id":      2,
		"method":  "shutdown",
	}
	shutdownBytes, _ := EncodePayload(shutdownReq)

	var inBuf bytes.Buffer
	inBuf.Write(initBytes)
	inBuf.Write(shutdownBytes)

	var outBuf bytes.Buffer
	cfg := config.DefaultConfig()

	server := NewServer(cfg, &inBuf, &outBuf)
	err := server.Start()
	if err != nil && err != io.EOF {
		t.Fatalf("unexpected server start error: %v", err)
	}

	outStr := outBuf.String()
	if !strings.Contains(outStr, `"capabilities":{"textDocumentSync":1}`) {
		t.Errorf("expected textDocumentSync in initialize response, got: %s", outStr)
	}
	if !strings.Contains(outStr, `"id":1`) {
		t.Errorf("expected response id 1 in output, got: %s", outStr)
	}
	if !strings.Contains(outStr, `"id":2`) {
		t.Errorf("expected response id 2 in output, got: %s", outStr)
	}
}

func TestConvertFeedbackToDiagnostics(t *testing.T) {
	cfg := config.DefaultConfig()
	server := NewServer(cfg, nil, nil)

	lines := []string{
		"package main",
		"var x = 1",
		"var y = 2",
	}

	feedback := "2: Unused variable x.\n3: Unused variable y.\nContinuation details."

	diags := server.ConvertFeedbackToDiagnostics("file:///main.go", feedback, lines)

	if len(diags) != 2 {
		t.Fatalf("expected 2 diagnostics, got %d", len(diags))
	}

	if diags[0].Range.Start.Line != 1 || diags[0].Message != "Unused variable x." {
		t.Errorf("unexpected diag 0: %+v", diags[0])
	}
	if diags[1].Range.Start.Line != 2 || diags[1].Message != "Unused variable y.\nContinuation details." {
		t.Errorf("unexpected diag 1: %+v", diags[1])
	}
}

func TestDebounceTimer(t *testing.T) {
	cfg := config.DefaultConfig()
	cfg.Debounce = 0.05

	var outBuf bytes.Buffer
	server := NewServer(cfg, nil, &outBuf)

	didOpen := map[string]any{
		"jsonrpc": "2.0",
		"method":  "textDocument/didOpen",
		"params": map[string]any{
			"textDocument": map[string]any{
				"uri":  "file:///test.py",
				"text": "print('hello')",
			},
		},
	}

	server.handleDidOpen(didOpen)

	server.timerMu.Lock()
	timer, hasTimer := server.reviewTimers["file:///test.py"]
	server.timerMu.Unlock()

	if !hasTimer || timer == nil {
		t.Errorf("expected debounce timer to be scheduled for test.py")
	}

	didClose := map[string]any{
		"jsonrpc": "2.0",
		"method":  "textDocument/didClose",
		"params": map[string]any{
			"textDocument": map[string]any{
				"uri": "file:///test.py",
			},
		},
	}
	server.handleDidClose(didClose)

	server.timerMu.Lock()
	_, hasTimerAfterClose := server.reviewTimers["file:///test.py"]
	server.timerMu.Unlock()

	if hasTimerAfterClose {
		t.Errorf("expected timer to be cancelled on didClose")
	}
}

func TestHeaderlessJsonFallback(t *testing.T) {
	rawJSON := `{"jsonrpc":"2.0","id":10,"method":"shutdown"}` + "\n"
	var inBuf bytes.Buffer
	inBuf.WriteString(rawJSON)

	var outBuf bytes.Buffer
	cfg := config.DefaultConfig()

	server := NewServer(cfg, &inBuf, &outBuf)
	err := server.Start()
	if err != nil && err != io.EOF {
		t.Fatalf("unexpected server start error: %v", err)
	}

	var resp map[string]any
	outLines := strings.Split(outBuf.String(), "\r\n\r\n")
	if len(outLines) < 2 {
		t.Fatalf("expected framed response, got: %s", outBuf.String())
	}
	if err := json.Unmarshal([]byte(outLines[1]), &resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if resp["id"] != float64(10) {
		t.Errorf("expected id 10, got %v", resp["id"])
	}
}
