def centers(widths: list[float], total: float) -> list[float]:
    """
    Given a list of widths and the total width, return the center positions of each width.
    """
    edge = -total / 2
    out = []
    for w in widths:
        out.append(edge + w / 2)
        edge += w
    return out
