"""Whitespace spans with stable source offsets, heading and fence boundaries."""

import re
from bisect import bisect_left, bisect_right


def chunk_text(normalized, media_type):
    # shortcut: whitespace units are provisional; verify model token limits before hosted embedding in 3C.
    tokens = list(re.finditer(r"\S+", normalized))
    positions = [token.start() for token in tokens]
    code_blocks, opening = [], None
    fences = re.finditer(r"^ {0,3}(`{3,}|~{3,}).*$", normalized, re.MULTILINE) if media_type == "text/markdown" else []
    for fence in fences:
        marker = fence.group(1)
        if opening is None:
            opening = (fence.start(), marker)
        elif marker[0] == opening[1][0] and len(marker) >= len(opening[1]):
            code_blocks.append((opening[0], fence.end()))
            opening = None
    if opening:
        code_blocks.append((opening[0], len(normalized)))
    code_starts = [start for start, _ in code_blocks]
    headings = list(re.finditer(r"^#{1,6}\s+(.+)$", normalized, re.MULTILINE)) if media_type == "text/markdown" else []
    visible_headings = []
    for heading in headings:
        index = bisect_right(code_starts, heading.start()) - 1
        if index < 0 or heading.start() >= code_blocks[index][1]:
            visible_headings.append(heading)
    headings = visible_headings
    heading_starts = [heading.start() for heading in headings]
    newlines = [match.start() for match in re.finditer("\n", normalized)]
    chunks = []
    start_token = 0
    while start_token < len(tokens):
        stop_token = min(start_token + 350, len(tokens))
        start = 0 if not start_token else tokens[start_token].start()
        end = len(normalized) if stop_token == len(tokens) else tokens[stop_token].start()
        boundaries = []
        next_heading = bisect_right(heading_starts, start)
        if next_heading < len(headings) and headings[next_heading].start() < end:
            boundaries.append(headings[next_heading].start())
        code_index = bisect_right(code_starts, end) - 1
        if code_index >= 0:
            left, right = code_blocks[code_index]
            if start < left < end < right and bisect_left(positions, right) - bisect_left(positions, left) <= 350:
                boundaries.append(left)
        structured = bool(boundaries)
        if structured:
            stop_token = bisect_left(positions, min(boundaries))
            end = tokens[stop_token].start()
        heading_index = bisect_right(heading_starts, start) - 1
        heading = headings[heading_index].group(1) if heading_index >= 0 else None
        if heading is None and headings and headings[0].start() < end:
            heading = headings[0].group(1)
        chunks.append({"start": start, "end": end, "heading": heading,
            "line_start": bisect_left(newlines, start) + 1,
            "line_end": bisect_left(newlines, end - 1) + 1})
        if len(chunks) > 10_000:
            raise ValueError("Too many text chunks")
        if stop_token == len(tokens):
            break
        start_token = stop_token if structured else stop_token - 50
    return chunks
