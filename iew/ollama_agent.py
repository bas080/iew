import subprocess, json, re


def agent_review(filepath, file_content):
    """Simple Ollama-based review."""
    prompt = f"Review this code and output feedback in format: line: message. Only output lines with issues.\n\n{file_content[:2000]}"
    
    try:
        result = subprocess.run(
            ["ollama", "run", "llama3", prompt],
            capture_output=True, text=True, timeout=30
        )
        output = result.stdout
        
        # Extract iew-format lines from AI output
        feedback = []
        for line in output.split('\n'):
            coord = __import__('iew.format').format.parse_coordinate(line)
            if coord and coord[0] != 'read':
                feedback.append(line)
        
        return '\n'.join(feedback) if feedback else output
    except Exception as e:
        return f"read: error: {e}"