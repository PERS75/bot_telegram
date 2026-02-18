def points_text(delta: int) -> str:
    """
    Возвращает строку вида:
    +1 очко, +2 очка, +5 очков
    −1 очко, −2 очка, −5 очков
    """
    n = abs(delta)

    if n % 10 == 1 and n % 100 != 11:
        word = "очко"
    elif 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        word = "очка"
    else:
        word = "очков"

    sign = "+" if delta > 0 else "−"
    return f"{sign}{n} {word}"