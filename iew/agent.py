import subprocess
import json
import os
import sys
import tempfile
import logging
import logging.handlers

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

LOGGER = logging.getLogger(__name__)


def get_config(config_path=None, verbose=False):
    """Read ~/.config/iew/iew.toml using tomllib."""
    if isinstance(config_path, bool):
        verbose = config_path
        config_path = None

    default_config = {
        "model": "llama3",
        "log_dir": None,
        "log_level": "INFO",
        "debounce": 15,
        "ollama_timeout": 180,
        "prompt": None,
    }

    if config_path is None:
        config_path = os.path.expanduser("~/.config/iew/iew.toml")

    if not os.path.exists(config_path):
        if verbose:
            LOGGER.debug("No config found at %s, using defaults", config_path)
        return default_config

    try:
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
        merged = dict(default_config)
        merged.update(config)
        if verbose:
            LOGGER.debug("Config loaded: %s", merged)
        return merged
    except Exception as e:
        LOGGER.debug("Config error: %s", e)
        return default_config


def build_prompt(config, display_name, numbered_lines):
    """Build the AI review prompt, using config['prompt'] if set, or a default prompt.

    The prompt is designed to be flexible and non-restrictive regarding review criteria,
    while explicitly specifying the output format (<line>: <description>).
    """
    custom_prompt = config.get("prompt") if config else None

    output_format_instructions = (
        "Output format instructions:\n"
        "- Each finding MUST start with a line number and a colon and a space:\n"
        "  <line>: <concise description of issue>\n"
        "- Output ONLY the formatted issue lines (one per line). If no issues exist, leave response completely blank.\n\n"
        "Examples of valid output:\n"
        "12: Hardcoded credentials detected.\n"
        "45: Unused variable 'unused_val'."
    )

    if not custom_prompt or not str(custom_prompt).strip():
        return (
            f"Review the following code file: {display_name}\n"
            f"Provide code review feedback for any issues, bugs, or improvements.\n\n"
            f"Code with line numbers:\n"
            f"{numbered_lines}\n\n"
            f"{output_format_instructions}"
        )

    template_vars = {
        "display_name": display_name,
        "filename": display_name,
        "file": display_name,
        "numbered_lines": numbered_lines,
        "code": numbered_lines,
    }

    custom_str = str(custom_prompt)
    has_code = "{numbered_lines}" in custom_str or "{code}" in custom_str
    prompt_text = custom_str
    for k, v in template_vars.items():
        prompt_text = prompt_text.replace(f"{{{k}}}", v)

    if has_code:
        if "<line>:" not in prompt_text and "Output format" not in prompt_text:
            prompt_text = f"{prompt_text}\n\n{output_format_instructions}"
        return prompt_text
    else:
        return (
            f"{prompt_text}\n\n"
            f"Code file: {display_name}\n\n"
            f"Code with line numbers:\n"
            f"{numbered_lines}\n\n"
            f"{output_format_instructions}"
        )


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

    def review_file(self, filepath, original_path=None):
        LOGGER.info("Reviewing file: %s", filepath)
        try:
            content = self.read_file(filepath)
        except Exception as e:
            LOGGER.error("Read error: %s", e)
            return f"error: {e}"

        feedback = []
        lines = content.split('\n')
        LOGGER.info("Scanning %d lines for issues", len(lines))

        # AI enhancement via Ollama
        try:
            display_name = os.path.basename(original_path or filepath)
            numbered_lines = '\n'.join(f"{idx} | {line}" for idx, line in enumerate(lines, 1))

            config = get_config(verbose=self.verbose)
            model = config.get("model", "llama3")
            LOGGER.info("Using Ollama model: %s", model)

            timeout = float(config.get("ollama_timeout", 180))
            LOGGER.info("Using Ollama timeout: %s", timeout)

            system_prompt = build_prompt(config, display_name, numbered_lines)

            # TODO: Consider using not curl but something python http client.
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
                    if coord and line not in feedback:
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
