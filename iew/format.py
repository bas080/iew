import re


def parse_coordinate(line):
    """Parse iew-format coordinate line.

    Supported formats:
    - 12: Unused variable.
    - Line 12: Unused variable.
    - 12:feedback
    - Line 12:feedback
    """
    line = line.strip()
    if not line:
        return None

    # Match digits followed by a colon anywhere in the line
    match = re.search(r"(\d+):", line)
    if not match:
        return None

    line_num = int(match.group(1))
    # Text after the matched digits and colon
    text = line[match.end():].strip()
    return ("line", line_num, text)
