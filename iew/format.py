def parse_coordinate(line):
    """Parse iew-format coordinate line.

    Supported format:
    - 12: Unused variable.
    """
    line = line.strip()
    if not line:
        return None

    if ':' not in line:
        return None

    parts = line.split(':', 1)
    if parts[0].isdigit():
        line_num = int(parts[0])
        text = parts[1].strip()
        return ('line', line_num, text)

    return None
