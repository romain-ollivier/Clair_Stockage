"""Pure geometry, shared by the UI and area-conservation tests."""
from __future__ import annotations

GIB = 1000**3
BANDS = [(10*GIB, '#e95a64', 'Très volumineux · ≥ 10 Go'),
         (GIB, '#ef9a46', 'Volumineux · ≥ 1 Go'),
         (100*1000**2, '#d7bd49', 'Moyen · ≥ 100 Mo'),
         (0, '#43a890', 'Petit · < 100 Mo')]


def band(size):
    return next((color, label) for threshold, color, label in BANDS if size >= threshold)


def size_text(size):
    # Decimal units: 1 Mo = 1 000 000 octets, 1 Go = 1 000 Mo.
    value = max(0, size)
    if value >= 1_000_000_000:
        return f'{value/1_000_000_000:,.2f} Go'.replace(',', ' ').replace('.', ',')
    if 0 < value < 10_000:
        return '< 0,01 Mo'
    return f'{value/1_000_000:,.2f} Mo'.replace(',', ' ').replace('.', ',')


def parent_share(size, total):
    """Return no percentage for an empty or stale parent snapshot."""
    if size is None or total <= 0 or size > total:
        return None
    return size / total


def share_text(size, total, complete=True):
    ratio = parent_share(size, total)
    if ratio is None:
        return '—'
    return ('≈ ' if not complete else '') + f'{ratio*100:.1f} %'.replace('.', ',')


def treemap(items, x, y, width, height):
    """Squarified rectangles (key, x, y, w, h), positive weights only."""
    positive = [(key, float(weight)) for key, weight in items if weight > 0]
    total = sum(weight for _, weight in positive)
    if not total or width <= 0 or height <= 0:
        return []
    todo = sorted([(key, weight*width*height/total) for key, weight in positive], key=lambda item: item[1], reverse=True)
    output = []

    def worst(row, side):
        values = [item[1] for item in row]
        s = sum(values)
        return max(side*side*max(values)/(s*s), s*s/(side*side*min(values)))

    def place(row, bx, by, w, h):
        area = sum(item[1] for item in row)
        if w >= h:
            column = min(w, area/h)
            offset = by
            for key, a in row:
                rh = min(by+h-offset, a/column)
                output.append((key, bx, offset, column, max(0, rh)))
                offset += rh
            return bx+column, by, max(0, w-column), h
        row_height = min(h, area/w)
        offset = bx
        for key, a in row:
            rw = min(bx+w-offset, a/row_height)
            output.append((key, offset, by, max(0, rw), row_height))
            offset += rw
        return bx, by+row_height, w, max(0, h-row_height)

    row = []
    for item in todo:
        side = min(width, height)
        if row and worst(row+[item], side) > worst(row, side):
            x, y, width, height = place(row, x, y, width, height)
            row = []
        row.append(item)
    if row and width > 0 and height > 0:
        place(row, x, y, width, height)
    return output
