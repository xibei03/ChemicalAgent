"""从原文里读数：写法的各种变体都要认出来，宁可多认，不可漏认。

这些是抄写检查的地基：漏认一种写法，合法的输入就会被报“数值在原文里找不到”，任务落到
NEEDS_INPUT 或 FAILED。
"""

import pytest

from reactor_agent.spec.numbers import candidate_numbers, has_numbers


def found(text: str) -> set[float]:
    return set(candidate_numbers(text))


def test_plain_and_full_width_digits_are_read():
    assert {10000.0, 2.5, 50.0} <= found("流量 10000 kg/h，２.５ MPa，转化率50%")


def test_a_thousands_separator_is_read_as_one_number():
    assert 10000.0 in found("流量 10,000 kg/h")


def test_a_comma_list_is_read_as_separate_numbers():
    # “600,700,800”既可能是一个千分位数，也可能是三个数，两种读法都留着
    numbers = found("出口温度 600，700，800 ℃")
    assert {600.0, 700.0, 800.0} <= numbers
    assert 600700800.0 in numbers


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("压力 1.2e5 Pa", 120000.0),
        ("压力 1.5×10^5 Pa", 150000.0),
        ("压力 2 x 10^-3 bar", 0.002),
        ("常数 3.0E2", 300.0),
        ("压力 10^5 Pa", 100000.0),
        ("浓度 10^-3 mol/L", 0.001),
    ],
)
def test_scientific_notation_is_read_as_its_value(text, value):
    assert value in found(text)


@pytest.mark.parametrize(("text", "value"), [("压力 2,5 MPa", 2.5), ("转化率 33,3 %", 33.3)])
def test_a_decimal_comma_is_read_as_a_decimal_point(text, value):
    assert value in found(text)


def test_a_comma_followed_by_three_digits_is_a_thousands_separator_not_a_decimal():
    numbers = found("流量 1,500 kg/h")
    assert 1500.0 in numbers
    assert 1.5 not in numbers


def test_a_leading_decimal_point_is_read():
    assert 0.5 in found("压降 .5 bar")


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("三百八十摄氏度", 380.0),
        ("两兆帕", 2.0),
        ("一万二千公斤每小时", 12000.0),
        ("二零二六", 2026.0),
        ("三点五兆帕", 3.5),
        ("十个大气压", 10.0),
        ("五十", 50.0),
    ],
)
def test_chinese_numerals_are_read(text, value):
    assert value in found(text)


@pytest.mark.parametrize("word", ["常压", "室温", "标准状态"])
def test_a_quantity_said_in_words_stands_for_its_usual_values(word):
    assert found(f"在{word}下反应"), word


def test_atmospheric_pressure_in_words_covers_the_usual_units():
    assert {1.0, 1.01325, 101.325} <= found("在常压下反应")


def test_digits_stuck_to_letters_are_not_numbers_given_in_the_text():
    assert not has_numbers("C7H8 与 H2O 反应，用 Nm3 表示")


def test_a_number_beside_a_formula_still_counts():
    assert has_numbers("H2O 流量 10 kg/h")


def test_a_text_with_only_chinese_numerals_has_numbers():
    assert has_numbers("温度三百八十摄氏度")


def test_a_text_without_any_digit_has_no_numbers():
    assert not has_numbers("把进料送进反应器，告诉我出口组成")
    assert candidate_numbers("") == ()


def test_a_lone_decimal_point_word_is_not_a_number():
    assert not has_numbers("点到为止，好的")
