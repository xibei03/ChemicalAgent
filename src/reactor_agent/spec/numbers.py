"""从原文里读出全部可能的数：阿拉伯数字（千分位、逗号列表、科学计数法）、汉字数字、文字说的量。

抄写检查用它判断“LLM 写的这个数，原文里有没有”。宁可多认：多认出来的数只会让检查更宽松，
漏认会把合法的输入误报成抄错。同一段文字里有几种读法时（“600,700”是一个数还是两个）都留着。
"""

import re
import unicodedata
from collections.abc import Mapping
from types import MappingProxyType

PLAIN = re.compile(r"\d+(?:\.\d+)?|\.\d+")
THOUSANDS = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?")
SCIENTIFIC = re.compile(r"(\d+(?:\.\d+)?)\s*(?:[eE]|[×xX*]\s*10\s*\^?)\s*([+\-−]?\d+)")
# “10^5 Pa”：只写了十的幂。
POWER_OF_TEN = re.compile(r"(?<![\d.])10\s*\^\s*([+\-−]?\d+)")
# “2,5 MPa”：小数点写成逗号；逗号后面是三位数字的是千分位，不在这里。
DECIMAL_COMMA = re.compile(r"(?<![\d,.])(\d+),(\d{1,2})(?!\d)")
# 紧贴字母的数字（H2O、C7H8、Nm3）是分子式或单位的一部分，不算原文给的数。
STANDALONE_DIGIT = re.compile(r"(?<![A-Za-z])\d")
CHINESE_RUN = re.compile(r"[零〇一二两三四五六七八九十百千万亿点]+")

DIGITS: Mapping[str, int] = MappingProxyType(
    {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7}
    | {"八": 8, "九": 9}
)
SMALL_UNITS: Mapping[str, int] = MappingProxyType({"十": 10, "百": 100, "千": 1000})
BIG_UNITS: Mapping[str, int] = MappingProxyType({"万": 10_000, "亿": 100_000_000})
# 用文字说出的量，和它们通常代表的数（常压是 1 atm，也就是 1.01325 bar、101.325 kPa）。
WORD_VALUES: Mapping[str, tuple[float, ...]] = MappingProxyType(
    {
        "常压": (1.0, 1.01325, 101.325),
        "大气压": (1.0, 1.01325, 101.325),
        "室温": (20.0, 25.0, 293.15, 298.15),
        "常温": (20.0, 25.0, 293.15, 298.15),
        "标准状态": (0.0, 1.0, 1.01325, 101.325, 273.15),
        "标况": (0.0, 1.0, 1.01325, 101.325, 273.15),
    }
)


def _integer(text: str) -> int:
    """汉字写的整数：三百八十、一万二千、二零二六。"""
    if not any(ch in SMALL_UNITS or ch in BIG_UNITS for ch in text):
        return int("".join(str(DIGITS[ch]) for ch in text) or 0)
    total = section = digit = 0
    for ch in text:
        if ch in DIGITS:
            digit = DIGITS[ch]
        elif ch in SMALL_UNITS:
            section += (digit or 1) * SMALL_UNITS[ch]
            digit = 0
        else:
            total += (section + digit) * BIG_UNITS[ch]
            section = digit = 0
    return total + section + digit


def _chinese_value(run: str) -> float | None:
    """一串汉字数字的值；只有“点”或者不成数的是 None。"""
    whole, _, fraction = run.partition("点")
    if not any(ch in DIGITS or ch in SMALL_UNITS or ch in BIG_UNITS for ch in whole + fraction):
        return None
    if any(ch in SMALL_UNITS or ch in BIG_UNITS for ch in fraction):
        return None
    decimals = "".join(str(DIGITS[ch]) for ch in fraction)
    return float(f"{_integer(whole)}.{decimals}") if decimals else float(_integer(whole))


def _arabic(flat: str) -> list[float]:
    numbers = [float(match) for match in PLAIN.findall(flat)]
    numbers += [float(match.replace(",", "")) for match in THOUSANDS.findall(flat)]
    for mantissa, exponent in SCIENTIFIC.findall(flat):
        numbers.append(float(mantissa) * 10 ** int(exponent.replace("−", "-")))
    numbers += [10.0 ** int(exponent.replace("−", "-")) for exponent in POWER_OF_TEN.findall(flat)]
    numbers += [float(f"{whole}.{fraction}") for whole, fraction in DECIMAL_COMMA.findall(flat)]
    return numbers


def candidate_numbers(text: str) -> tuple[float, ...]:
    """原文里可能出现的全部数（非负）：阿拉伯数字、汉字数字，和原文里文字说的量代表的数。"""
    flat = unicodedata.normalize("NFKC", text)
    numbers = _arabic(flat)
    numbers += [v for run in CHINESE_RUN.findall(flat) if (v := _chinese_value(run)) is not None]
    for word, values in WORD_VALUES.items():
        if word in flat:
            numbers += values
    return tuple(numbers)


def has_numbers(text: str) -> bool:
    """原文里有没有数：不紧贴字母的阿拉伯数字，或者汉字数字。"""
    flat = unicodedata.normalize("NFKC", text)
    if STANDALONE_DIGIT.search(flat):
        return True
    return any(_chinese_value(run) is not None for run in CHINESE_RUN.findall(flat))
