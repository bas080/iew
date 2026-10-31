def parse_coordinate(line):
    """Parse iew-format coordinate lines.

    Supported formats from README:
    - 12: Unused variable.               (line only)
    - 45:2: Missing quote.              (single-line char offset)
    - 78:0-78:15: Hardcoded secret.     (multi-line range without line number)
    - 102-105: Inefficient loop.        (multi-line range without explicit line number)
    - 150:0-150:8: Error handling missing. (full coordinate pair with line number)
    - read: main.mjs                    (file read request)
    - 150:0-150:8: Error handling missing. read: substring match
    """
    line = line.strip()
    if not line:
        return None

    # Case: read: requests
    if line.startswith('read:'):
        filepath = line[5:].strip()
        return ('read', filepath)

    # Count colons to determine format
    colon_count = line.count(':')

    # Case: Multi-line range WITH line number (e.g., "150:0-150:8: Error handling missing.")
    # Format: "line:start_char-end_line:end_char: text"  -> 3+ colons
    if colon_count >= 3:
        parts = line.split(':', 3)
        if parts[0].isdigit():
            line_num = int(parts[0])
            if '-' in parts[1]:
                coords = parts[1].split('-', 1)
                if len(coords) == 2:
                    start_char = int(coords[0]) if coords[0].isdigit() else 0
                    # end_line is the second number in the range (if it's a line number)
                    # or treat the whole range as char offsets on the same line
                    end_line_str = coords[1].split(':')[0] if ':' in coords[1] else coords[1]
                    end_line = int(end_line_str) if end_line_str.isdigit() else line_num
                    end_char_str = coords[1].split(':')[1] if ':' in coords[1] else parts[2] if len(parts) > 2 else '0'
                    end_char = int(end_char_str) if end_char_str.isdigit() else 0
                    text = parts[3].strip() if len(parts) > 3 else ''
                    return ('pair', line_num, start_char, end_line, end_char, text)

    # Case: Multi-line range WITHOUT line number (e.g., "102-105: Inefficient loop.")
    # Format: "start-end: text" where start may start with digit or dash
    if line.startswith('-') or (colon_count == 1 and '-' in line):
        parts = line.split(':', 1)
        if len(parts) >= 2:
            start_end = parts[0].strip()
            if '-' in start_end:
                start_str, end_str = start_end.split('-', 1)
                # Allow start to be digit-only or dash-prefixed
                start_is_digit = start_str.isdigit()
                end_is_digit = end_str.isdigit()
                if (start_is_digit or start_str == '') and end_is_digit:
                    start = int(start_str) if start_is_digit else 0
                    end = int(end_str)
                    text = parts[1].strip() if len(parts) > 1 else ''
                    return ('multiline_range', start, end, text)

    # Case 1: Line-only (e.g., "12: Unused variable.")
    if colon_count == 1:
        parts = line.split(':', 1)
        if parts[0].isdigit():
            line_num = int(parts[0])
            return ('line', line_num, parts[1].strip())

    # Case 2: Single-line char offset (e.g., "45:2: Missing quote.")
    if colon_count == 2:
        parts = line.split(':', 2)
        if parts[0].isdigit() and parts[1].isdigit():
            line_num = int(parts[0])
            char_offset = int(parts[1])
            return ('offset', line_num, char_offset, parts[2].strip())

    return None