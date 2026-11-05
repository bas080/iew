package lsp

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/iew-org/iew/internal/agent"
	"github.com/iew-org/iew/internal/config"
	"github.com/iew-org/iew/internal/format"
)

// Position in a document (0-based).
type Position struct {
	Line      int `json:"line"`
	Character int `json:"character"`
}

// Range in a document.
type Range struct {
	Start Position `json:"start"`
	End   Position `json:"end"`
}

// Diagnostic represents an LSP diagnostic message.
type Diagnostic struct {
	Range    Range  `json:"range"`
	Message  string `json:"message"`
	Severity int    `json:"severity"` // 1: Error, 2: Warning, 3: Information, 4: Hint
	Source   string `json:"source"`
}

// Server is a read-only LSP server over stdio.
type Server struct {
	config        *config.Config
	agent         *agent.Agent
	documentStore map[string]string
	reviewTimers  map[string]*time.Timer
	timerMu       sync.Mutex
	writeMu       sync.Mutex
	in            io.Reader
	out           io.Writer
}

func NewServer(cfg *config.Config, in io.Reader, out io.Writer) *Server {
	return &Server{
		config:        cfg,
		agent:         agent.NewAgent(cfg),
		documentStore: make(map[string]string),
		reviewTimers:  make(map[string]*time.Timer),
		in:            in,
		out:           out,
	}
}

// Start begins processing LSP messages until EOF or exit.
func (s *Server) Start() error {
	slog.Info("Starting iew LSP server...")
	reader := bufio.NewReader(s.in)

	for {
		msg, err := s.readMessage(reader)
		if err != nil {
			if err == io.EOF {
				return nil
			}
			slog.Error("Read message error", "err", err)
			return err
		}

		if err := s.handleMessage(msg); err != nil {
			slog.Error("Handle message error", "err", err)
		}
	}
}

func (s *Server) readMessage(reader *bufio.Reader) (map[string]any, error) {
	contentLength := -1

	for {
		line, err := reader.ReadString('\n')
		if err != nil {
			return nil, err
		}

		lineTrimmed := strings.TrimSpace(line)
		if lineTrimmed == "" {
			if contentLength >= 0 {
				break
			}
			continue
		}

		lower := strings.ToLower(lineTrimmed)
		if strings.HasPrefix(lower, "content-length:") {
			parts := strings.SplitN(lineTrimmed, ":", 2)
			if len(parts) == 2 {
				val, err := strconv.Atoi(strings.TrimSpace(parts[1]))
				if err == nil {
					contentLength = val
				}
			}
		} else if strings.HasPrefix(lineTrimmed, "{") {
			// Fallback for headerless raw JSON lines
			var raw map[string]any
			if err := json.Unmarshal([]byte(lineTrimmed), &raw); err == nil {
				return raw, nil
			}
		}
	}

	if contentLength >= 0 {
		buf := make([]byte, contentLength)
		if _, err := io.ReadFull(reader, buf); err != nil {
			return nil, err
		}

		var raw map[string]any
		if err := json.Unmarshal(buf, &raw); err != nil {
			return nil, fmt.Errorf("JSON decode error: %w", err)
		}
		return raw, nil
	}

	return nil, fmt.Errorf("invalid LSP framing")
}

func (s *Server) SendPayload(payload any) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	header := fmt.Sprintf("Content-Length: %d\r\n\r\n", len(body))

	s.writeMu.Lock()
	defer s.writeMu.Unlock()

	if _, err := s.out.Write([]byte(header)); err != nil {
		return err
	}
	if _, err := s.out.Write(body); err != nil {
		return err
	}
	return nil
}

func (s *Server) handleMessage(msg map[string]any) error {
	method, _ := msg["method"].(string)
	msgID := msg["id"]

	slog.Debug("Handling LSP message", "method", method, "id", msgID)

	switch method {
	case "initialize":
		return s.handleInitialize(msgID)
	case "initialized":
		return nil
	case "textDocument/didOpen":
		return s.handleDidOpen(msg)
	case "textDocument/didChange":
		return s.handleDidChange(msg)
	case "textDocument/didSave":
		return s.handleDidSave(msg)
	case "textDocument/didClose":
		return s.handleDidClose(msg)
	case "shutdown":
		return s.handleShutdown(msgID)
	case "exit":
		os.Exit(0)
		return nil
	default:
		if msgID != nil {
			return s.respondError(msgID, -32601, fmt.Sprintf("Method %s not supported", method))
		}
		slog.Debug("Ignored unhandled notification", "method", method)
		return nil
	}
}

func (s *Server) handleInitialize(msgID any) error {
	resp := map[string]any{
		"jsonrpc": "2.0",
		"id":      msgID,
		"result": map[string]any{
			"capabilities": map[string]any{
				"textDocumentSync": 1,
			},
		},
	}
	return s.SendPayload(resp)
}

func (s *Server) handleDidOpen(msg map[string]any) error {
	params, _ := msg["params"].(map[string]any)
	doc := s.extractTextDocument(params)
	uri, _ := doc["uri"].(string)
	content, _ := doc["text"].(string)

	s.timerMu.Lock()
	s.documentStore[uri] = content
	s.timerMu.Unlock()

	s.triggerReview(uri, content)
	return nil
}

func (s *Server) handleDidChange(msg map[string]any) error {
	params, _ := msg["params"].(map[string]any)
	doc := s.extractTextDocument(params)
	uri, _ := doc["uri"].(string)

	var content string
	if changes, ok := params["contentChanges"].([]any); ok && len(changes) > 0 {
		if lastChange, ok := changes[len(changes)-1].(map[string]any); ok {
			content, _ = lastChange["text"].(string)
		}
	} else if c, ok := doc["content"].(string); ok {
		content = c
	} else if t, ok := doc["text"].(string); ok {
		content = t
	} else {
		s.timerMu.Lock()
		content = s.documentStore[uri]
		s.timerMu.Unlock()
	}

	s.timerMu.Lock()
	s.documentStore[uri] = content
	s.timerMu.Unlock()

	s.triggerReview(uri, content)
	return nil
}

func (s *Server) handleDidSave(msg map[string]any) error {
	params, _ := msg["params"].(map[string]any)
	doc := s.extractTextDocument(params)
	uri, _ := doc["uri"].(string)

	s.timerMu.Lock()
	content, ok := s.documentStore[uri]
	s.timerMu.Unlock()

	if ok {
		s.triggerReview(uri, content)
	}
	return nil
}

func (s *Server) handleDidClose(msg map[string]any) error {
	params, _ := msg["params"].(map[string]any)
	doc := s.extractTextDocument(params)
	uri, _ := doc["uri"].(string)

	s.timerMu.Lock()
	if timer, ok := s.reviewTimers[uri]; ok {
		timer.Stop()
		delete(s.reviewTimers, uri)
	}
	delete(s.documentStore, uri)
	s.timerMu.Unlock()
	return nil
}

func (s *Server) handleShutdown(msgID any) error {
	s.timerMu.Lock()
	for _, timer := range s.reviewTimers {
		timer.Stop()
	}
	s.reviewTimers = make(map[string]*time.Timer)
	s.timerMu.Unlock()

	resp := map[string]any{
		"jsonrpc": "2.0",
		"id":      msgID,
		"result":  nil,
	}
	return s.SendPayload(resp)
}

func (s *Server) respondError(msgID any, code int, msg string) error {
	resp := map[string]any{
		"jsonrpc": "2.0",
		"id":      msgID,
		"error": map[string]any{
			"code":    code,
			"message": msg,
		},
	}
	return s.SendPayload(resp)
}

func (s *Server) extractTextDocument(params map[string]any) map[string]any {
	if doc, ok := params["textDocument"].(map[string]any); ok {
		return doc
	}
	if doc, ok := params["text_document"].(map[string]any); ok {
		return doc
	}
	return make(map[string]any)
}

func (s *Server) triggerReview(uri, content string) {
	debounceSec := s.config.Debounce
	d := time.Duration(debounceSec * float64(time.Second))

	s.timerMu.Lock()
	defer s.timerMu.Unlock()

	if timer, ok := s.reviewTimers[uri]; ok {
		timer.Stop()
	}

	s.reviewTimers[uri] = time.AfterFunc(d, func() {
		s.reviewWorker(uri, content)
	})
}

func (s *Server) reviewWorker(uri, content string) {
	filePath := strings.TrimPrefix(uri, "file://")

	s.timerMu.Lock()
	currentContent, ok := s.documentStore[uri]
	s.timerMu.Unlock()
	if ok {
		content = currentContent
	}

	feedback, err := s.agent.ReviewContent(filePath, content)
	if err != nil {
		slog.Error("Review worker error", "uri", uri, "err", err)
	}

	lines := strings.Split(content, "\n")
	diagnostics := s.ConvertFeedbackToDiagnostics(uri, feedback, lines)
	if err := s.PublishDiagnostics(uri, diagnostics); err != nil {
		slog.Error("Publish diagnostics error", "uri", uri, "err", err)
	}
}

func (s *Server) ConvertFeedbackToDiagnostics(uri, feedbackText string, lines []string) []Diagnostic {
	var diagnostics []Diagnostic
	if strings.TrimSpace(feedbackText) == "" {
		return diagnostics
	}

	var currentCoord *format.Coordinate

	for _, rawLine := range strings.Split(feedbackText, "\n") {
		trimmed := strings.TrimSpace(rawLine)
		if trimmed == "" {
			continue
		}

		coord := format.ParseCoordinate(trimmed)
		if coord != nil {
			if currentCoord != nil {
				if d := s.coordToDiagnostic(currentCoord, lines); d != nil {
					diagnostics = append(diagnostics, *d)
				}
			}
			currentCoord = coord
		} else if currentCoord != nil {
			if currentCoord.Message != "" {
				currentCoord.Message = fmt.Sprintf("%s\n%s", currentCoord.Message, trimmed)
			} else {
				currentCoord.Message = trimmed
			}
		}
	}

	if currentCoord != nil {
		if d := s.coordToDiagnostic(currentCoord, lines); d != nil {
			diagnostics = append(diagnostics, *d)
		}
	}

	return diagnostics
}

func (s *Server) coordToDiagnostic(coord *format.Coordinate, lines []string) *Diagnostic {
	if coord == nil || coord.Kind != "line" || coord.Message == "" {
		return nil
	}

	startLine := coord.LineNum - 1
	if startLine < 0 {
		startLine = 0
	}
	endLine := startLine

	startChar := 0
	endChar := 100
	if lines != nil && startLine >= 0 && startLine < len(lines) {
		lineLen := len(lines[startLine])
		if lineLen < 1 {
			endChar = 1
		} else {
			endChar = lineLen
		}
	}

	return &Diagnostic{
		Range: Range{
			Start: Position{Line: startLine, Character: startChar},
			End:   Position{Line: endLine, Character: endChar},
		},
		Message:  coord.Message,
		Severity: 2,
		Source:   "iew",
	}
}

func (s *Server) PublishDiagnostics(uri string, diagnostics []Diagnostic) error {
	notification := map[string]any{
		"jsonrpc": "2.0",
		"method":  "textDocument/publishDiagnostics",
		"params": map[string]any{
			"uri":         uri,
			"diagnostics": diagnostics,
		},
	}
	return s.SendPayload(notification)
}

func EncodePayload(payload any) ([]byte, error) {
	b, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	var buf bytes.Buffer
	buf.WriteString(fmt.Sprintf("Content-Length: %d\r\n\r\n", len(b)))
	buf.Write(b)
	return buf.Bytes(), nil
}
