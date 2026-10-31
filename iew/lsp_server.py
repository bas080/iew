import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from lsprotocol import types

from .agent import Agent
from .format import parse_coordinate


def get_debounce():
    try:
        from .agent import get_config
        cfg = get_config()
        val = cfg.get("debounce", 15)
        return float(val) if val else 15
    except Exception:
        return 15


LOGGER = logging.getLogger(__name__)


def setup_lsp_logger(verbose=False):
    """Configure logger to write to stderr only (never corrupt stdout LSP stream)."""
    LOGGER.setLevel(logging.DEBUG if verbose else logging.INFO)
    LOGGER.handlers.clear()
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter("%(name)s: %(levelname)s: %(message)s"))
    LOGGER.addHandler(h)


from .agent import Agent

DEBOUNCE_DEFAULT = 15


class SimpleLSP:
    """Read-only AI code review LSP server compatible with Helix and other editors."""

    def __init__(self, verbose=False):
        self.verbose = verbose
        self.agent = Agent(verbose=verbose)
        self.document_store = {}
        self.review_timers = {}
        self.timer_lock = threading.Lock()
        self.write_lock = threading.Lock()

    def start(self):
        """Start the LSP server reading messages from stdin."""
        setup_lsp_logger(self.verbose)
        LOGGER.info("Starting iew LSP server...")

        try:
            while True:
                message = self.read_message()
                if message is None:
                    break
                self.handle_message(message)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            LOGGER.error("Server error: %s", e)

    def read_message(self):
        """Read a single LSP message from stdin, handling Content-Length headers."""
        content_length = None
        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                return None  # EOF
            line_stripped = line.strip()
            if not line_stripped:
                if content_length is not None:
                    break
                continue
            if line_stripped.lower().startswith(b"content-length:"):
                parts = line_stripped.split(b":", 1)
                try:
                    content_length = int(parts[1].strip())
                except ValueError:
                    pass
            elif line_stripped.startswith(b"{"):
                # Fallback for headerless raw JSON lines
                try:
                    return json.loads(line_stripped.decode("utf-8"))
                except Exception:
                    pass

        if content_length is not None:
            body = sys.stdin.buffer.read(content_length)
            try:
                return json.loads(body.decode("utf-8"))
            except Exception as e:
                LOGGER.error("JSON decode error: %s", e)
                return None
        return None

    def send_payload(self, payload):
        """Send a message to stdout with standard LSP Content-Length framing."""
        body = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
        with self.write_lock:
            sys.stdout.buffer.write(header + body)
            sys.stdout.buffer.flush()

    def handle_message(self, message):
        """Handle incoming LSP message."""
        if not isinstance(message, dict):
            return

        method = message.get("method", "")
        msg_id = message.get("id")

        LOGGER.debug("Handling LSP message: method=%s, id=%s", method, msg_id)

        if method == "initialize":
            self.handle_initialize(message)
        elif method == "initialized":
            # Client notification confirming initialization; no response needed
            pass
        elif method == "textDocument/didOpen":
            self.handle_did_open(message)
        elif method == "textDocument/didChange":
            self.handle_did_change(message)
        elif method == "textDocument/didSave":
            self.handle_did_save(message)
        elif method == "textDocument/didClose":
            self.handle_did_close(message)
        elif method == "shutdown":
            self.handle_shutdown(message)
        elif method == "exit":
            self.handle_exit()
        else:
            if msg_id is not None:
                self.respond_error(msg_id, -32601, f"Method {method} not supported")
            else:
                LOGGER.debug("Ignored unhandled notification: %s", method)

    def handle_initialize(self, message):
        """Handle LSP initialize request."""
        response = {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "result": {
                "capabilities": {
                    "textDocumentSync": 1,  # Full document sync
                }
            }
        }
        self.send_payload(response)

    def handle_did_open(self, message):
        """Handle textDocument/didOpen notification."""
        params = message.get("params", {})
        doc = params.get("textDocument") or params.get("text_document") or {}
        uri = doc.get("uri", "")
        content = doc.get("text", "")

        self.document_store[uri] = content
        self._trigger_review(uri, content)

    def handle_did_change(self, message):
        """Handle textDocument/didChange notification."""
        params = message.get("params", {})
        doc = params.get("textDocument") or params.get("text_document") or {}
        uri = doc.get("uri", "")

        changes = params.get("contentChanges", [])
        if changes:
            # Full sync sends the complete document text in the change event
            content = changes[-1].get("text", "")
        elif "content" in doc:
            content = doc.get("content", "")
        elif "text" in doc:
            content = doc.get("text", "")
        else:
            content = self.document_store.get(uri, "")

        self.document_store[uri] = content
        self._trigger_review(uri, content)

    def handle_did_save(self, message):
        """Handle textDocument/didSave notification."""
        params = message.get("params", {})
        doc = params.get("textDocument") or params.get("text_document") or {}
        uri = doc.get("uri", "")
        if uri in self.document_store:
            self._trigger_review(uri, self.document_store[uri])

    def handle_did_close(self, message):
        """Handle textDocument/didClose notification."""
        params = message.get("params", {})
        doc = params.get("textDocument") or params.get("text_document") or {}
        uri = doc.get("uri", "")
        with self.timer_lock:
            timer = self.review_timers.pop(uri, None)
            if timer:
                timer.cancel()
        self.document_store.pop(uri, None)

    def handle_shutdown(self, message):
        """Handle shutdown request."""
        with self.timer_lock:
            for timer in self.review_timers.values():
                timer.cancel()
            self.review_timers.clear()

        response = {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "result": None
        }
        self.send_payload(response)

    def handle_exit(self):
        """Handle exit notification."""
        sys.exit(0)

    def respond_error(self, msg_id, code, error_msg):
        """Send JSON-RPC error response."""
        response = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": code,
                "message": error_msg
            }
        }
        self.send_payload(response)

    def publish_diagnostics(self, uri, diagnostics):
        """Publish diagnostics notification to client."""
        notification = {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {
                "uri": uri,
                "diagnostics": [self.convert_diagnostic(d) for d in diagnostics]
            }
        }
        self.send_payload(notification)

    def _trigger_review(self, uri, content):
        """Schedule debounced AI review."""
        with self.timer_lock:
            if uri in self.review_timers:
                self.review_timers[uri].cancel()

            timer = threading.Timer(get_debounce(), self._review_worker, args=(uri, content))
            self.review_timers[uri] = timer
            timer.daemon = True
            timer.start()

    def _review_worker(self, uri, content):
        """Background thread executing review with Ollama."""
        try:
            temp_file = self._create_temp_file(uri, content)
            try:
                original_path = uri.replace("file://", "")
                feedback = self.agent.review_file(temp_file, original_path=original_path)
            finally:
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

            if uri in self.document_store:
                lines = self.document_store[uri].split('\n')
                diagnostics = self.convert_feedback_to_diagnostics(uri, feedback, lines=lines)
                self.publish_diagnostics(uri, diagnostics)
        except Exception as e:
            LOGGER.error("Review worker error for %s: %s", uri, e)

    def _create_temp_file(self, uri, content):
        """Create temporary file for review preserving file extension."""
        file_path = uri.replace('file://', '')
        _, ext = os.path.splitext(file_path)
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=ext or '.tmp') as f:
            f.write(content)
            return f.name

    def convert_feedback_to_diagnostics(self, uri, feedback_text, lines=None):
        """Convert iew-format feedback lines to Diagnostic objects."""
        diagnostics = []
        if not feedback_text:
            return diagnostics

        for line in feedback_text.split('\n'):
            line = line.strip()
            if not line:
                continue

            coord = parse_coordinate(line)
            if not coord:
                continue

            diag = self._coord_to_diagnostic(coord, lines=lines)
            if diag:
                diagnostics.append(diag)
        return diagnostics

    def _coord_to_diagnostic(self, coord, lines=None):
        """Convert coordinate tuple to Diagnostic."""
        msg = None
        start_line = 0
        start_char = 0
        end_line = 0
        end_char = 100

        if coord[0] == 'line':
            start_line = max(0, coord[1] - 1)
            end_line = start_line
            start_char = 0
            if lines and 0 <= start_line < len(lines):
                end_char = max(1, len(lines[start_line]))
            else:
                end_char = 100
            msg = coord[2]

        if msg:
            return types.Diagnostic(
                range=types.Range(
                    start=types.Position(line=start_line, character=start_char),
                    end=types.Position(line=end_line, character=end_char)
                ),
                message=msg,
                severity=types.DiagnosticSeverity.Warning,
                source="iew"
            )
        return None

    def convert_diagnostic(self, diagnostic):
        """Convert Diagnostic to LSP dict."""
        sev = diagnostic.severity
        sev_value = sev.value if hasattr(sev, 'value') else int(sev)
        return {
            "range": {
                "start": {
                    "line": diagnostic.range.start.line,
                    "character": diagnostic.range.start.character
                },
                "end": {
                    "line": diagnostic.range.end.line,
                    "character": diagnostic.range.end.character
                }
            },
            "message": diagnostic.message,
            "severity": sev_value,
            "source": diagnostic.source or "iew"
        }


# Global server instance
_server = SimpleLSP()


def main():
    """Entry point for the LSP server."""
    try:
        _server.start()
    except Exception as e:
        LOGGER.error("LSP server failed to start: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
