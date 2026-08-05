"""Charset-specific radar symbols."""


def symbols(charset: str) -> dict[str, str]:
    if charset == "unicode":
        return {
            "receiver": "⊕",
            "aircraft": "▲",
            "climb": "↑",
            "descend": "↓",
            "ground": "◇",
            "emergency": "!",
            "trail": "·",
            "ring": "·",
            "collision": "*",
        }
    if charset == "cp437":
        return {
            "receiver": "+",
            "aircraft": "▲",
            "climb": "↑",
            "descend": "↓",
            "ground": "o",
            "emergency": "!",
            "trail": ".",
            "ring": ".",
            "collision": "*",
        }
    return {
        "receiver": "+",
        "aircraft": "^",
        "climb": "^",
        "descend": "v",
        "ground": "o",
        "emergency": "!",
        "trail": ".",
        "ring": ".",
        "collision": "*",
    }
