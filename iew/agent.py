import subprocess
import json
import os
import sys
import tempfile
import logging
import logging.handlers

LOGGER = logging.getLogger(__name__)


def get_config(verbose=False):
    """Read ~/.config/iew/iew.toml"""
    config_path = os.path.expanduser("~/.config/iew/iew.toml")
    if not os.path.exists(config_path):
        if verbose:
            LOGGER.debug("No config found, using default model")
        return {"model": "llama3", "log_dir": None, "log_level": "INFO", "debounce": 15, "ollama_timeout": 180}
    try:
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
            LOGGER.debug("Config loaded: %s", config)
        return config
    except Exception as e:
        LOGGER.debug("Config error: %s", e)
        return {"model": "llama3", "log_dir": None, "log_level": "INFO", "debounce": 15, "ollama_timeout": 180}


def setup_agent_logger(verbose=False):
    """Configure agent logger with rotation from config."""
    config = get_config()
    log_dir = config.get("log_dir")
    log_level_name = config.get("log_level", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    LOGGER.setLevel(log_level)
    # Clear existing handlers to avoid duplicates
    LOGGER.handlers.clear()

    # Always log to stderr (safe for LSP mode — never stdout)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(log_level)
    stderr_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    LOGGER.addHandler(stderr_handler)

    if log_dir:
        try:
            os.makedirs(log_dir, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                os.path.join(log_dir, "iew_agent.log"),
                maxBytes=1024 * 1024,  # 1MB rotation cap
                backupCount=3
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s %(levelname)s: %(message)s"
            ))
            LOGGER.addHandler(file_handler)
        except Exception as e:
            LOGGER.warning("Failed to set up file handler: %s", e)


class Agent:
    def __init__(self, verbose=False):
        self.verbose = verbose
        setup_agent_logger(verbose=verbose)
        LOGGER.debug("Agent initialized (verbose=%s)", verbose)

    def read_file(self, path):
        LOGGER.info("Reading file: %s", path)
        with open(path, 'r') as f:
            return f.read()

    def review_file(self, filepath, original_path=None, scan_todos=True):
        LOGGER.info("Reviewing file: %s", filepath)
        try:
            content = self.read_file(filepath)
        except Exception as e:
            LOGGER.error("Read error: %s", e)
            return f"read: error: {e}"

        feedback = []
        lines = content.split('\n')
        LOGGER.info("Scanning %d lines for issues", len(lines))

        # Scan for TODOs if enabled
        if scan_todos:
            for i, line in enumerate(lines, 1):
                if 'TODO' in line:
                    feedback.append(f"{i}: TODO found")
                    LOGGER.info("Line %d: TODO found", i)

        # Scan for read: directives
        for i, line in enumerate(lines, 1):
            if 'read:' in line:
                parts = line.split('read:', 1)
                if len(parts) > 1 and parts[1].strip():
                    search_term = parts[1].strip()
                    matches = self._fuzzy_file_search(search_term)
                    for match in matches[:3]:
                        feedback.append(f"read: {match}")
                        LOGGER.info("Read request: %s", match)

        # AI enhancement via Ollama
        try:
            display_name = os.path.basename(original_path or filepath)
            numbered_lines = '\n'.join(f"{idx} | {line}" for idx, line in enumerate(lines, 1))

            system_prompt = (
                f"You are an expert AI code reviewer.\n"
                f"Review the following code file: {display_name}\n"
                f"Identify bugs, security vulnerabilities (such as hardcoded credentials, command injection, unsafe calls), "
                f"syntax errors, unhandled exceptions, unused variables or imports, and important TODO/FIXME comments that require developer attention.\n\n"
                f"Code with line numbers:\n"
                f"{numbered_lines}\n\n"
                f"Output format instructions:\n"
                f"- Each finding MUST start with a line number or line range, followed by a colon and a space:\n"
                f"  <line>: <concise description of issue>\n"
                f"  or\n"
                f"  <start_line>-<end_line>: <concise description of issue>\n"
                f"- Use the exact line numbers from the numbered code above.\n"
                f"- Do NOT wrap lines in quotes or backticks.\n"
                f"- Do NOT output markdown bullet points, asterisks, headers, summaries, or explanations.\n"
                f"- Output ONLY the formatted issue lines. If no issues exist, leave response completely blank.\n\n"
                f"Examples of valid output:\n"
                f"12: Hardcoded credentials detected.\n"
                f"45: Unused variable 'unused_val'.\n"
                f"78-82: Inefficient loop.\n"
            )

            config = get_config(verbose=self.verbose)
            model = config.get("model", "llama3")
            LOGGER.info("Using Ollama model: %s", model)

            cfg = get_config(verbose=self.verbose)
            timeout = float(cfg.get("ollama_timeout", 180))
            LOGGER.info("Using Ollama timeout: %s", timeout)

            response = subprocess.run(
                ["curl", "-s", "-X", "POST", "http://localhost:11434/api/generate",
                 "-H", "Content-Type: application/json",
                 "-d", json.dumps({"model": model, "prompt": system_prompt, "stream": False})],
                capture_output=True, text=True, timeout=timeout
            )

            if response.returncode == 0:
                data = json.loads(response.stdout)
                output = data.get("response", "")
                LOGGER.info("Ollama response received (%d chars)", len(output))

                import iew.format
                for raw_line in output.split('\n'):
                    line = raw_line.strip().strip('"\'`')
                    if line.startswith(("- ", "* ")):
                        line = line[2:].strip().strip('"\'`')
                    if not line:
                        continue
                    coord = iew.format.parse_coordinate(line)
                    if coord and coord[0] != 'read' and line not in feedback:
                        feedback.append(line)
                        LOGGER.info("Added AI feedback: %s", line)
            else:
                LOGGER.error("Ollama API error: %s", response.stderr)
        except subprocess.TimeoutExpired:
            LOGGER.warning("Ollama request timed out")
        except Exception as e:
            LOGGER.error("Ollama error: %s", e)

        LOGGER.info("Total feedback lines: %d", len(feedback))
        return '\n'.join(feedback) if feedback else ""

    def _fuzzy_file_search(self, term):
        LOGGER.info("Fuzzy file search for: %s", term)
        matches = []
        for root, dirs, files in os.walk('.'):
            for f in files:
                full_path = os.path.join(root, f)
                if term.lower() in full_path.lower():
                    matches.append(full_path)
        LOGGER.info("Fuzzy search found %d matches", len(matches))
        return matches
