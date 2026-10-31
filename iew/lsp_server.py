from lsprotocol import types
import json
import sys
import os
import subprocess
import threading
import time
import tempfile

from .agent import Agent
from .format import parse_coordinate

class SimpleLSP:
    """Simple LSP server implementation based on lsprotocol."""

    def __init__(self, verbose=False):
        self.verbose = verbose
        self.agent = Agent(verbose=verbose)
        self.document_store = {}

    def _debug(self, msg):
        if self.verbose:
            print(f"[DEBUG] {msg}", flush=True)

    def start(self):
        """Start the LSP server."""
        print("Starting iew LSP server...", flush=True)

        try:
            for line in sys.stdin:
                if line.strip():
                    self.handle_message(line)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"Server error: {e}", flush=True)

    def handle_message(self, data):
        """Handle incoming LSP messages."""
        try:
            message = json.loads(data)
            msg_type = message.get('method', '')

            if msg_type == 'initialize':
                self.handle_initialize(message)
            elif msg_type == 'textDocument/didOpen':
                self.handle_did_open(message)
            elif msg_type == 'textDocument/didChange':
                self.handle_did_change(message)
            elif msg_type == 'shutdown':
                self.handle_shutdown(message)
            elif msg_type == 'exit':
                self.handle_exit()
            else:
                self.respond_error(message, f"Method {msg_type} not supported")

        except json.JSONDecodeError:
            self.respond_error(None, "Invalid JSON")
        except Exception as e:
            self.respond_error(message, f"Error: {str(e)}")

    def handle_initialize(self, message):
        """Handle LSP initialization."""
        response = {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "result": {
                "capabilities": {
                    "textDocumentSync": 1,  # Basic sync
                    "diagnosticProvider": {
                        "identifier": "iew",
                        "workDoneProgress": False
                    }
                }
            }
        }

        self.send_response(response)

    def handle_did_open(self, message):
        """Handle textDocument/didOpen."""
        params = message.get('params', {})
        text_document = params.get('text_document', {})
        uri = text_document.get('uri', '')
        content = text_document.get('text', '')

        # Store document content
        self.document_store[uri] = content

        # Create temp file for agent to review
        temp_file = self._create_temp_file(uri, content)
        feedback = self.agent.review_file(temp_file)

        # Convert to diagnostics
        diagnostics = self.convert_feedback_to_diagnostics(uri, feedback)

        # Publish diagnostics
        self.publish_diagnostics(uri, diagnostics)

    def handle_did_change(self, message):
        """Handle textDocument/didChange."""
        params = message.get('params', {})
        text_document = params.get('text_document', {})
        uri = text_document.get('uri', '')

        # Update document content
        if 'content' in text_document:
            self.document_store[uri] = text_document['content']

        # Create temp file and review
        temp_file = self._create_temp_file(uri, self.document_store.get(uri, ''))
        feedback = self.agent.review_file(temp_file)
        diagnostics = self.convert_feedback_to_diagnostics(uri, feedback)

        self.publish_diagnostics(uri, diagnostics)

    def _create_temp_file(self, uri, content):
        """Create temporary file for review."""
        # Remove file:// prefix if present
        file_path = uri.replace('file://', '')
        # Use tempfile for safety
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tmp') as f:
            f.write(content)
            return f.name

    def handle_shutdown(self, message):
        """Handle shutdown request."""
        response = {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "result": None
        }
        self.send_response(response)

    def handle_exit(self):
        """Handle exit request."""
        sys.exit(0)

    def respond_error(self, message, error_msg):
        """Send error response."""
        response = {
            "jsonrpc": "2.0",
            "id": message.get("id") if message else None,
            "error": {
                "code": -32600,
                "message": error_msg
            }
        }
        self.send_response(response)

    def send_response(self, response):
        """Send response to stdout."""
        print(json.dumps(response), flush=True)

    def publish_diagnostics(self, uri, diagnostics):
        """Publish diagnostics to stdout."""
        notification = {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {
                "uri": uri,
                "diagnostics": [self.convert_diagnostic(d) for d in diagnostics]
            }
        }
        print(json.dumps(notification), flush=True)

    def convert_feedback_to_diagnostics(self, uri, feedback_text):
        """Convert iew-format feedback to diagnostics."""
        diagnostics = []
        if not feedback_text:
            return diagnostics

        # Parse the provided feedback directly (read-only, no re-review)
        for line in feedback_text.split('\n'):
            line = line.strip()
            if not line or line.startswith('read:'):
                continue

            coord = parse_coordinate(line)
            if not coord:
                continue

            diag = self._coord_to_diagnostic(coord)
            if diag:
                diagnostics.append(diag)
        return diagnostics

    def _coord_to_diagnostic(self, coord):
        """Convert coordinate tuple to Diagnostic."""
        msg = None
        start_line = 0
        start_char = 0
        end_line = 0
        end_char = 100

        if coord[0] == 'line':
            start_line = coord[1] - 1
            end_line = start_line
            msg = coord[2]
        elif coord[0] == 'offset':
            start_line = coord[1] - 1
            start_char = coord[2]
            end_line = start_line
            end_char = start_char + 1
            msg = coord[3]
        elif coord[0] == 'pair':
            start_line = coord[1] - 1
            start_char = coord[2]
            end_line = coord[3] - 1
            end_char = coord[4]
            msg = coord[5]
        elif coord[0] == 'multiline_range':
            start_line = coord[1] - 1
            end_line = coord[2] - 1
            msg = coord[3]

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
            "severity": diagnostic.severity,
            "source": diagnostic.source
        }

# Global server instance
_server = SimpleLSP()

def main():
    """Entry point for the LSP server."""
    try:
        _server.start()
    except Exception as e:
        print(f"LSP server failed to start: {e}", flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()