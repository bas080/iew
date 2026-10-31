# Testing Guide

## Overview
This project contains end-to-end tests in the `tests/` directory to verify functionality of the iew code review tool.

## Prerequisites
- Python 3.8+
- pytest (7.2.1+) - can be installed via pip
- Required Python packages: lsprotocol, pygls (used by tests)
- Ollama running locally (required for LSP tests)

## How to Run Tests

### Quick Test Run
Run all 16 tests (including LSP test which needs Ollama):

```bash
python3 -m pytest tests/ -v
```

**Test Results**: All 16 tests pass ✓

### Run Specific Tests
Run a single test:

```bash
python3 -m pytest tests/e2e_test.py::test_parse_coordinate_line -v
```

Run tests for specific functionality:

```bash
# Parse coordinate tests
python3 -m pytest tests/ -v -k "parse_coordinate"

# CLI tests
python3 -m pytest tests/ -v -k "cli"

# LSP tests
python3 -m pytest tests/ -v -k "lsp"
```

### Test Structure
The `tests/e2e_test.py` file contains the following test categories:

### 1. Configuration & Prompt Tests
- `test_get_config_defaults`: Verifies default configuration when file does not exist
- `test_get_config_custom_toml`: Verifies loading custom settings via `tomllib`
- `test_build_prompt_default`: Verifies flexible default review prompt with line-number output format
- `test_build_prompt_custom_instruction`: Verifies custom prompt instruction preserves output format
- `test_build_prompt_custom_template`: Verifies placeholder substitution for custom templates
- `test_agent_uses_configured_prompt`: Verifies Agent uses configured prompt during review

### 2. Coordinate Parsing Tests
- `test_parse_coordinate_line`: Tests `line:` format parsing
- `test_parse_coordinate_simple_only`: Tests line parsing with colons in message
- `test_parse_coordinate_empty`: Tests empty input handling
- `test_parse_coordinate_garbage`: Tests garbage input handling

### 4. CLI Entry Point Tests
- `test_cli_no_args_exits`: Verifies the CLI exits with error when no filepath is provided
- `test_cli_reviews_file`: Verifies the CLI prints feedback to stdout

### 5. LSP Bin Script End-to-End Test
- `test_bin_lsp_initialize_and_review`: Tests the `iew-lsp` binary script starts correctly, responds to LSP initialize messages, and handles didOpen events

## Test Dependencies
The tests use these dependencies:
- `pytest`: Testing framework
- `lsprotocol` & `pygls`: For LSP-related tests
- `unittest.mock`: For mocking in tests
- `subprocess`: For running the LSP server binary

If you encounter import errors, install them:

```bash
pip install pytest lsprotocol pygls
```

## Debug Output
Many tests can be run with verbose output to see more details. Use the `-v` flag with pytest to see which tests are running and their status.

Some components of the code (like `Agent`) have a `--verbose` flag that can be used from the command line:

```bash
iew --verbose /path/to/file.js
```

## Test Time Requirements
The LSP test (`test_bin_lsp_initialize_and_review`) requires:
- ~30 seconds to complete
- Ollama running locally with the `llama3` model
- Sufficient time for Ollama to process the test file and generate feedback

All non-LSP tests complete in ~30-90 seconds total.

## CI/CD Integration
These tests can be integrated into CI/CD pipelines using:

```yaml
# Example for GitHub Actions - allows longer timeout for LSP test
- name: Run tests
  run: |
    timeout 360 python3 -m pytest tests/ -v
```

## Troubleshooting

### Common Issues:

1. **Test timeouts**:
   - The LSP test needs ~30 seconds and Ollama running
   - Use `timeout 360 python3 -m pytest tests/ -v` to give it 6 minutes
   - Ensure Ollama is running with `ollama list`

2. **Import errors**:
   - Install missing dependencies with `pip install pytest lsprotocol pygls`

3. **Test failures**:
   - Look at the error output for specific failures
   - Check if Ollama is running for LSP tests

### Running Tests Manually
If you want to test functionality outside of pytest:

```bash
# Test the main iew command
iew /path/to/your/file.js

# Test the LSP server
bin/iew-lsp
```

Note: The iew command may wait for Ollama to be running before producing output.

## Debugging with Ollama
If LSP tests fail due to Ollama issues:

```bash
# Check if Ollama is running
ollama list

# Start Ollama if not running
ollama serve

# Pull the default model if needed
ollama pull llama3
```

All 16 tests pass successfully when all dependencies are met!
