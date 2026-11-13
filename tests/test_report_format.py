from milan_cdr.report import fmt, markdown_table


def test_fmt_spanish_number_format():
    assert fmt(1234567) == "1.234.567"
    assert fmt(1234.5) == "1.234,50"
    assert fmt("Italia") == "Italia"
    assert fmt(None) == "None"
    assert fmt(88239, "_id") == "88239"


def test_markdown_table():
    table = markdown_table([{"a": 1, "b": 2.5}], ("a", "b"), ("A", "B"))
    assert table.splitlines() == ["| A | B |", "|---|---|", "| 1 | 2,50 |"]
