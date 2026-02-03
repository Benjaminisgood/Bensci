"""
文本清洗工具。

Elsevier XML 中包含大量 Unicode 特殊字符，这里沿用 L2M3 的正则替换逻辑，
但只保留硬检索需要的 `clean_text` 方法。
"""

import regex


def clean_text(text: str) -> str:
    """把段落中的非标准字符替换为常见 ASCII，便于匹配和嵌入。"""
    unicode_space = r"[\u2000-\u2005\u2007\u2008]|\xa0|\n|&nbsp|\t"  # 各类空白符
    unicode_waste = r"[\u2006\u2009-\u200F]|\u00ad|\u202f|\u205f"  # 零宽字符
    unicode_minus = r"[\u2010-\u2015]|\u2212"  # 各种短横线
    unicode_wave = r"≈|∼"  # 波浪符
    unicode_quote = r"\u2032|\u201B|\u2019"  # 单引号变体
    unicode_doublequote = r"\u201C|\u201D|\u2033"  # 双引号变体
    unicode_slash = r"\u2215"  # 斜杠
    unicode_rest = r"\u201A"  # 下标逗号
    unicode_middle_dot = r"\u2022|\u2024|\u2027|\u00B7"  # 中点

    text = text.replace("\n", " ")
    text = regex.sub(unicode_space, " ", text)
    text = regex.sub(unicode_waste, "", text)
    text = regex.sub(unicode_minus, "-", text)
    text = regex.sub(unicode_wave, "~", text)
    text = regex.sub(unicode_quote, "' ", text)
    text = regex.sub(unicode_doublequote, '"', text)
    text = regex.sub(unicode_slash, "/", text)
    text = regex.sub(unicode_rest, ",", text)
    text = regex.sub(unicode_middle_dot, "\u22C5", text)

    return text.strip()

