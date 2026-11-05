package main

import (
	"flag"
	"fmt"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"strings"

	"github.com/iew-org/iew/internal/adapter"
	"github.com/iew-org/iew/internal/config"
	"github.com/iew-org/iew/internal/lsp"
)

func setupLogger(cfg *config.Config, verbose bool) {
	level := slog.LevelInfo
	if verbose || strings.ToUpper(cfg.LogLevel) == "DEBUG" {
		level = slog.LevelDebug
	}

	opts := &slog.HandlerOptions{
		Level: level,
	}

	var writers []io.Writer
	writers = append(writers, os.Stderr)

	logFilePath := cfg.LogFile
	if logFilePath != "" && strings.ToLower(logFilePath) != "/dev/null" {
		expanded := config.ExpandPath(logFilePath)
		if err := os.MkdirAll(filepath.Dir(expanded), 0755); err == nil {
			f, err := os.OpenFile(expanded, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
			if err == nil {
				writers = append(writers, f)
			}
		}
	}

	multi := io.MultiWriter(writers...)
	handler := slog.NewTextHandler(multi, opts)
	slog.SetDefault(slog.New(handler))
}

func runHealth(cfg *config.Config) {
	fmt.Printf("Loaded config: provider=%s, model=%s\n", cfg.Provider, cfg.Model)

	adp, err := adapter.GetAdapter(cfg)
	if err != nil {
		fmt.Printf("Error getting adapter: %s\n", err)
		os.Exit(1)
	}

	prompt := "hi"
	fmt.Printf("Sending '%s' to %s model '%s'...\n", prompt, cfg.Provider, cfg.Model)

	response, err := adp.Complete(prompt)
	if err != nil {
		fmt.Printf("Error sending request: %s\n", err)
		os.Exit(1)
	}

	fmt.Printf("Response: %s\n", response)

	logFile := cfg.LogFile
	if logFile == "" {
		logFile = "~/.config/iew/iew.log"
	}
	fmt.Printf("Logs are stored in %s\n", config.ExpandPath(logFile))
}

func main() {
	var health bool
	var verbose bool

	flag.BoolVar(&health, "health", false, "Send 'hi' to configured provider/model for debugging")
	flag.BoolVar(&verbose, "v", false, "Verbose debug output")
	flag.BoolVar(&verbose, "verbose", false, "Verbose debug output")
	flag.Parse()

	cfg := config.GetConfig("")
	setupLogger(cfg, verbose)

	if health {
		runHealth(cfg)
		return
	}

	server := lsp.NewServer(cfg, os.Stdin, os.Stdout)
	if err := server.Start(); err != nil {
		slog.Error("LSP server failed", "err", err)
		os.Exit(1)
	}
}
