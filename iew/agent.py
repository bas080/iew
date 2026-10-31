import subprocess
import json
import os
import sys
import tempfile


def get_config(verbose=False):
    """Read ~/.config/iew/iew.toml"""
    config_path = os.path.expanduser("~/.config/iew/iew.toml")
    if not os.path.exists(config_path):
        if verbose:
            print(f"[DEBUG] No config found, using default model", file=sys.stderr)
        return {"model": "llama3"}
    try:
        # Basic TOML parser for simple key = "value" format
        config = {}
        with open(config_path, 'r') as f:
            for line in f:
                line = line.split('#', 1)[0].strip()
                if '=' in line and not line.startswith('['):
                    key, val = line.split('=', 1)
                    key = key.strip()
                    val = val.strip()
                    if val.startswith('"') and val.endswith('"'):
                        val = val[1:-1]
                    config[key] = val
        if verbose:
            print(f"[DEBUG] Config loaded: {config}", file=sys.stderr)
        return config
    except Exception as e:
        if verbose:
            print(f"[DEBUG] Config error: {e}", file=sys.stderr)
        return {"model": "llama3"}


class Agent:
    def __init__(self, verbose=False):
        self.verbose = verbose

    def _debug(self, msg):
        if self.verbose:
            print(f"[DEBUG] {msg}", file=sys.stderr)

    def read_file(self, path):
        """Handle read: file/path requests."""
        self._debug(f"Reading file: {path}")
        with open(path, 'r') as f:
            return f.read()

    def review_file(self, filepath):
        """Generate iew-format feedback."""
        self._debug(f"Reviewing file: {filepath}")
        try:
            content = self.read_file(filepath)
        except Exception as e:
            return f"read: error: {e}"

        feedback = []
        lines = content.split('\n')
        self._debug(f"Scanning {len(lines)} lines for issues")

        # Scan for issues
        for i, line in enumerate(lines, 1):
            if 'TODO' in line:
                feedback.append(f"{i}: TODO found")
                self._debug(f"Line {i}: TODO found")
            if 'read:' in line:
                parts = line.split('read:', 1)
                if len(parts) > 1 and parts[1].strip():
                    search_term = parts[1].strip()
                    matches = self._fuzzy_file_search(search_term)
                    for match in matches[:3]:
                        feedback.append(f"read: {match}")
                        self._debug(f"Read request: {match}")

        # Try Ollama JSON API for AI enhancement
        try:
            system_prompt = (
                f"You are an AI code reviewer that helps developers identify issues in their code.\n\n"
                f"Filename: {filepath}\n\n"
                f"Your task is to review the provided code and output feedback in a specific format.\n"
                f"You must ONLY output lines that follow this exact format: \"line: message\" or \"coordinate: message\".\n"
                f"Do NOT output any other text, explanations, or code comments.\n"
                f"Each line must contain:\n"
                f"- A line number (e.g., \"12:\" for the 12th line)\n"
                f"- A colon and space\n"
                f"- A concise message describing the issue or finding\n\n"
                f"Examples of valid output:\n"
                f'  "12: Unused variable."\n'
                f'  "45:2: Missing quote."\n'
                f'  "78:0-78:15: Hardcoded secret."\n'
                f'  "102-105: Inefficient loop."\n'
                f'  "read: filename"\n\n'
                f"Review this code and output ONLY in the format described above:\n\n"
                f"=== {filepath} ===\n"
                f"{content}"
            )

            config = get_config(verbose=self.verbose)
            model = config.get("model", "llama3")
            self._debug(f"Using Ollama model: {model}")

            response = subprocess.run(
                ["curl", "-s", "-X", "POST", "http://localhost:11434/api/generate",
                 "-H", "Content-Type: application/json",
                 "-d", json.dumps({"model": model, "prompt": system_prompt, "stream": False})],
                capture_output=True, text=True, timeout=30
            )

            if response.returncode == 0:
                data = json.loads(response.stdout)
                output = data.get("response", "")
                self._debug(f"Ollama response received ({len(output)} chars)")

                import iew.format
                for line in output.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    coord = iew.format.parse_coordinate(line)
                    if coord and coord[0] != 'read' and line not in feedback:
                        feedback.append(line)
                        self._debug(f"Added AI feedback: {line}")
            else:
                print(f"Ollama API error: {response.stderr}", file=sys.stderr)
                self._debug(f"Ollama API error: {response.stderr}")
        except subprocess.TimeoutExpired:
            print("Ollama request timed out", file=sys.stderr)
            self._debug("Ollama request timed out")
        except Exception as e:
            print(f"Ollama error: {e}", file=sys.stderr)
            self._debug(f"Ollama error: {e}")

        self._debug(f"Total feedback lines: {len(feedback)}")
        return '\n'.join(feedback) if feedback else ""

    def _fuzzy_file_search(self, term):
        """Substring match files against search term."""
        self._debug(f"Fuzzy file search for: {term}")
        matches = []
        for root, dirs, files in os.walk('.'):
            for f in files:
                full_path = os.path.join(root, f)
                if term.lower() in full_path.lower():
                    matches.append(full_path)
        self._debug(f"Fuzzy search found {len(matches)} matches")
        return matches