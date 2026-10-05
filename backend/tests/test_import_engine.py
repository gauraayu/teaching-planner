"""Pure-logic tests for the import engine: parsing, mapping, row alignment, validation."""
from datetime import date, time

import pytest

from app.core.errors import AppError
from app.services import value_parsers as vp
from app.services.import_parsing import parse_column_text, parse_table_text
from app.services.mapping_service import detect_header_row, normalize_header, suggest_mapping
from app.services.validation_service import validate_rows


# ----------------------------------------------------------------- TSV parsing

def test_tsv_structure_rows_and_columns():
    text = "SrNo\tLecture_No\tContent_Topic\n1\t1\tIntroduction to Recursion\n2\t2\tMaster Theorem\n"
    grid = parse_table_text(text)
    assert grid.width == 3
    assert grid.rows == [["SrNo", "Lecture_No", "Content_Topic"], ["1", "1", "Introduction to Recursion"], ["2", "2", "Master Theorem"]]


def test_crlf_and_lf_normalised():
    assert parse_table_text("a\tb\r\n1\t2\r\n").rows == parse_table_text("a\tb\n1\t2").rows == [["a", "b"], ["1", "2"]]


def test_blank_cells_keep_their_position():
    # Row 2 has an empty middle cell, row 3 is missing trailing cells (as Sheets emits them).
    grid = parse_table_text("A\tB\tC\n1\t\t3\n4")
    assert grid.rows == [["A", "B", "C"], ["1", "", "3"], ["4", "", ""]]


def test_blank_rows_inside_data_are_preserved():
    grid = parse_table_text("A\tB\n1\tx\n\t\n3\tz")
    assert grid.rows[2] == ["", ""]
    assert grid.rows[3] == ["3", "z"]


def test_trailing_empty_rows_dropped_and_counted():
    grid = parse_table_text("A\tB\n1\t2\n\t\n\t\n")
    assert grid.height == 2
    assert grid.trailing_empty_rows_dropped == 2


def test_quoted_multiline_cell_from_sheets():
    text = 'Topic\tSubs\nQuick Sort\t"Lomuto partition\nHoare partition"\nMerge Sort\t"He said ""merge"""'
    grid = parse_table_text(text)
    assert grid.rows[1] == ["Quick Sort", "Lomuto partition\nHoare partition"]
    assert grid.rows[2] == ["Merge Sort", 'He said "merge"']


def test_surrounding_whitespace_trimmed_not_inner():
    grid = parse_table_text("  A \t B \n x  y \t ")
    assert grid.rows == [["A", "B"], ["x  y", ""]]


def test_empty_paste_rejected():
    with pytest.raises(AppError):
        parse_table_text("   \n ")


def test_column_paste_preserves_blank_values():
    values, notes = parse_column_text("K1\n\nK3\n")
    assert values == ["K1", "", "K3"]
    assert notes == []


def test_column_paste_with_multiple_columns_uses_first():
    values, notes = parse_column_text("a\tb\nc\td")
    assert values == ["a", "c"]
    assert notes


# ----------------------------------------------------------------- mapping

@pytest.mark.parametrize("header", ["Content Topic", "Content_Topic", "CONTENT-TOPIC", " content topic", "ContentTopic"])
def test_header_normalisation(header):
    assert normalize_header(header) == "content topic"


def test_normalise_digits_and_apostrophes():
    assert normalize_header("Sub_Topic1") == "sub topic 1"
    assert normalize_header("Bloom's Taxonomy") == "blooms taxonomy"


def _map(*headers):
    cols = [{"key": f"c{i}", "header": h, "values": []} for i, h in enumerate(headers)]
    return suggest_mapping(cols)


def test_exact_and_alias_mapping():
    m = _map("Lecture_No", "Unit_No", "Content_Topic", "Blooms_Taxonomy", "Scheduled_Date", "SrNo", "Lecture_Type")
    assert [m[f"c{i}"]["field"] for i in range(7)] == [
        "lecture_no", "unit_no", "content_topic", "blooms_taxonomy", "planned_date", "serial_no", "lecture_type"]
    assert all(v["status"] == "MAPPED" for v in m.values())
    assert m["c0"]["method"] in ("ALIAS", "EXACT")


def test_subtopic_columns_get_ordered():
    m = _map("Sub_Topic1", "Sub_Topic2", "Sub_Topic3")
    assert [(m[k]["field"], m[k]["order"]) for k in ("c0", "c1", "c2")] == [("subtopic", 1), ("subtopic", 2), ("subtopic", 3)]


def test_fuzzy_match_is_suggested_not_accepted():
    m = _map("Bloom Taxnomy")
    assert m["c0"]["field"] == "blooms_taxonomy"
    assert m["c0"]["status"] == "SUGGESTED"
    assert m["c0"]["method"] == "FUZZY"


def test_unknown_header_needs_review():
    m = _map("Learning Content")
    assert m["c0"]["status"] == "NEEDS_REVIEW"
    assert m["c0"]["field"] is None


def test_execution_columns_auto_ignored():
    m = _map("Remarks about Task Completion", "Verified by CL/HoI/CH", "Daily Lecture Notes Link", "Shared in Student Groups")
    assert all(v["status"] == "IGNORED" and v["method"] == "EXECUTION_COLUMN" for v in m.values())


def test_duplicate_single_field_demoted():
    m = _map("Topic", "Content Topic")
    statuses = sorted(v["status"] for v in m.values())
    assert statuses == ["MAPPED", "NEEDS_REVIEW"]


def test_value_profile_hint_for_headerless_bloom_column():
    cols = [{"key": "c0", "header": "Level", "values": ["K1", "K2", "K3", "K2"]}]
    m = suggest_mapping(cols)
    assert m["c0"]["status"] == "NEEDS_REVIEW"
    assert m["c0"]["suggestion"] == "blooms_taxonomy"


def test_header_detection():
    assert detect_header_row(["SrNo", "Lecture_No", "Content_Topic"], [["1", "1", "Recursion"]])
    assert not detect_header_row(["1", "1", "Recursion"], [["2", "2", "Fibonacci"]])


# ----------------------------------------------------------------- value parsers

@pytest.mark.parametrize("raw,expected", [("1", 1), ("1.0", 1), ("L1", 1), ("Lec-12", 12), ("Lecture 3", 3)])
def test_lecture_no(raw, expected):
    assert vp.parse_lecture_no(raw) == (expected, None)


def test_lecture_no_invalid():
    value, issue = vp.parse_lecture_no("1a")
    assert value is None and issue[0] == "ERROR"


@pytest.mark.parametrize("raw,expected", [("2", 2), ("Unit 3", 3), ("Unit-IV", 4), ("II", 2), ("U1", 1)])
def test_unit(raw, expected):
    assert vp.parse_unit(raw)[0] == expected


@pytest.mark.parametrize("raw,expected", [("K1", "K1"), ("k2", "K2"), ("L3", "K3"), ("Understand", "K2"), ("BT4", "K4"), ("3", "K3")])
def test_bloom(raw, expected):
    assert vp.parse_bloom(raw) == (expected, None)


def test_bloom_multiple_takes_highest_with_warning():
    value, issue = vp.parse_bloom("K2/K3")
    assert value == "K3" and issue[0] == "WARNING"


def test_bloom_invalid():
    assert vp.parse_bloom("K9")[1][0] == "ERROR"


@pytest.mark.parametrize("raw", ["01/10/2026", "1-10-2026", "2026-10-01", "01-Oct-2026", "1 October 2026",
                                 "Thursday, 1 October 2026", "1st Oct 2026", "46296", "01.10.26"])
def test_date_formats_dayfirst(raw):
    assert vp.parse_date(raw, dayfirst=True)[0] == date(2026, 10, 1)


def test_date_invalid():
    assert vp.parse_date("31/02/2026")[1][0] == "ERROR"


@pytest.mark.parametrize("raw,expected", [("10:00", time(10)), ("10:00 AM", time(10)), ("2 pm", time(14)), ("14.30", time(14, 30))])
def test_time(raw, expected):
    assert vp.parse_time(raw)[0] == expected


def test_subtopics_split_lines_and_bullets():
    assert vp.split_subtopics(["Definition", "• Base case\n2) Recursive case", ""]) == ["Definition", "Base case", "Recursive case"]


# ----------------------------------------------------------------- row alignment & validation

def _col(key, field, values, order=None):
    return ({"key": key, "header": field, "values": values},
            {key: {"field": field, "status": "MAPPED", "method": "MANUAL", "confidence": 100, "order": order}})


def _build(*cols):
    columns, mapping = [], {}
    for c, m in cols:
        columns.append(c)
        mapping.update(m)
    return columns, mapping


def test_column_wise_row_index_alignment():
    columns, mapping = _build(
        _col("t", "content_topic", ["Recursion", "Fibonacci", "Merge Sort"]),
        _col("n", "lecture_no", ["1", "2", "3"]),
        _col("u", "unit_no", ["1", "1", "2"]),
        _col("b", "blooms_taxonomy", ["K1", "K2", "K3"]),
    )
    result = validate_rows(columns, mapping)
    got = [(r["values"]["content_topic"], r["values"]["unit_no"], r["values"]["blooms_taxonomy"]) for r in result["rows"]]
    assert got == [("Recursion", 1, "K1"), ("Fibonacci", 1, "K2"), ("Merge Sort", 2, "K3")]


def test_blank_value_does_not_shift_following_rows():
    columns, mapping = _build(
        _col("t", "content_topic", ["Recursion", "Fibonacci", "Merge Sort"]),
        _col("n", "lecture_no", ["1", "2", "3"]),
        _col("b", "blooms_taxonomy", ["K1", "", "K3"]),
    )
    rows = validate_rows(columns, mapping)["rows"]
    assert rows[1]["values"]["blooms_taxonomy"] is None
    assert rows[2]["values"]["blooms_taxonomy"] == "K3"
    assert rows[1]["status"] == "WARNING"


def test_duplicate_lecture_numbers_are_errors():
    columns, mapping = _build(_col("t", "content_topic", ["A", "B"]), _col("n", "lecture_no", ["5", "5"]))
    result = validate_rows(columns, mapping)
    assert result["summary"]["errors"] == 2
    assert not result["can_commit"]


def test_missing_topic_and_bad_date_are_errors():
    columns, mapping = _build(
        _col("t", "content_topic", ["A", ""]), _col("n", "lecture_no", ["1", "2"]),
        _col("d", "planned_date", ["32/10/2026", "02/10/2026"]),
    )
    rows = validate_rows(columns, mapping)["rows"]
    assert rows[0]["status"] == "ERROR" and rows[1]["status"] == "ERROR"


def test_subtopic_columns_become_ordered_list():
    columns, mapping = _build(
        _col("t", "content_topic", ["Quick Sort"]), _col("n", "lecture_no", ["12"]),
        _col("s2", "subtopic", ["Lomuto partition"], order=2), _col("s1", "subtopic", ["Overview"], order=1),
        _col("s3", "subtopic", [""], order=3),
    )
    assert validate_rows(columns, mapping)["rows"][0]["values"]["subtopics"] == ["Overview", "Lomuto partition"]


def test_time_range_in_start_column_is_split():
    columns, mapping = _build(_col("t", "content_topic", ["A"]), _col("n", "lecture_no", ["1"]),
                              _col("d", "planned_date", ["01/10/2026"]), _col("s", "planned_start_time", ["10:00 - 11:00"]))
    v = validate_rows(columns, mapping)["rows"][0]["values"]
    assert (v["planned_start_time"], v["planned_end_time"]) == ("10:00", "11:00")


def test_required_mapping_missing_blocks_commit():
    columns, mapping = _build(_col("t", "content_topic", ["A"]))
    result = validate_rows(columns, mapping)
    assert any(i["code"] == "MAPPING_REQUIRED_MISSING" for i in result["session_issues"])
    assert not result["can_commit"]


def test_fill_down_is_explicit():
    columns, mapping = _build(_col("t", "content_topic", ["A", "B", "C"]), _col("n", "lecture_no", ["1", "2", "3"]),
                              _col("u", "unit_no", ["1", "", "2"]))
    assert validate_rows(columns, mapping)["rows"][1]["values"]["unit_no"] is None
    mapping["u"]["fill_down"] = True
    assert validate_rows(columns, mapping)["rows"][1]["values"]["unit_no"] == 1


def test_removed_and_empty_rows_excluded():
    columns, mapping = _build(_col("t", "content_topic", ["A", "", "C"]), _col("n", "lecture_no", ["1", "", "3"]))
    result = validate_rows(columns, mapping, removed=[2])
    assert [r["status"] for r in result["rows"]] == ["VALID", "EMPTY", "REMOVED"]
    assert result["summary"]["lectures"] == 1


def test_leading_empty_cell_does_not_shift_columns():
    grid = parse_table_text("\tB\tC\nx\ty\tz")
    assert grid.rows == [["", "B", "C"], ["x", "y", "z"]]
