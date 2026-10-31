import json
import logging
import logging.handlers
import os
import subprocess
import sys
import tempfile

from .adapters import get_adapter

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
        "ollama_model": "llama3",
        "provider": "ollama",
        "openrouter_model": "deepseek/deepseek-chat-v3-0324:free",
        "openrouter_key": None,
        "log_level": "INFO",
        "log_file": "~/.config/iew/iew.log",
        "debounce": 15,
        "timeout": 180,
        "max_retries": 3,
        "prompt": None,
        "keep_alive": "30m",
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
    """Build the AI review prompt, placing static instructions first for optimal KV cache reuse.

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
            "Review the code and provide code review feedback for any issues, bugs, or improvements.\n\n"
            f"{output_format_instructions}\n\n"
            f"Code file: {display_name}\n\n"
            "Code with line numbers:\n"
            f"{numbered_lines}"
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
            f"{output_format_instructions}\n\n"
            f"Code file: {display_name}\n\n"
            "Code with line numbers:\n"
            f"{numbered_lines}"
        )


def setup_agent_logger(verbose=False):
    """Configure agent logger with stderr and rotation in file (configurable via log_file)."""
    config = get_config()
    log_level_name = config.get("log_level", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    log_file = config.get("log_file", "~/.config/iew/iew.log")

    LOGGER.setLevel(log_level)
    # Clear existing handlers to avoid duplicates
    LOGGER.handlers.clear()

    # Always log to stderr (safe for LSP mode — never stdout)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(log_level)
    stderr_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    LOGGER.addHandler(stderr_handler)

    if log_file and str(log_file).lower() != "/dev/null":
        try:
            log_path = os.path.expanduser(str(log_file))
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                log_path,
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

    def _process_feedback(self, output, lines, feedback):
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

        # AI enhancement via configured provider adapter
        try:
            display_name = os.path.basename(original_path or filepath)
            numbered_lines = '\n'.join(f"{idx} | {line}" for idx, line in enumerate(lines, 1))

            config = get_config(verbose=self.verbose)
            system_prompt = build_prompt(config, display_name, numbered_lines)

            adapter = get_adapter(config)
            output = adapter.complete(system_prompt)
            if output:
                self._process_feedback(output, lines, feedback)
        except subprocess.TimeoutExpired:
            LOGGER.warning("Request timed out")
        except Exception as e:
            LOGGER.error("Review error: %s", e)
            return f"error: {e}"

        LOGGER.info("Total feedback lines: %d", len(feedback))
        return '\n'.join(feedback) if feedback else ""
