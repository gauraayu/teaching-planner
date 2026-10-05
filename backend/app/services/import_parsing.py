"""Turn raw spreadsheet input (clipboard text, .xlsx, .csv) into a rectangular grid of strings.

Every source ends up as the same `Grid` structure, which the rest of the import
pipeline consumes. Blank cells are preserved as "" - nothing is ever dropped in
a way that could shift a value into a different row or column.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime, time

from app.core.errors import AppError

NBSP = " "


@dataclass
class Grid:
    rows: list[list[str]]
    width: int
    trailing_empty_rows_dropped: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def height(self) -> int:
        return len(self.rows)


def _clean_cell(value: str) -> str:
    # Only surrounding whitespace is trimmed; inner newlines (multi-line cells) are meaningful.
    return value.replace(NBSP, " ").replace("\r\n", "\n").replace("\r", "\n").strip()


def _split_records(text: str) -> list[list[str]]:
    """RFC-4180-style TSV tokenizer as produced by Google Sheets and Excel.

    - "\t" separates cells, "\n" / "\r\n" / "\r" separate rows.
    - A cell that starts with a double quote is quoted: it may contain tabs,
      newlines and doubled quotes ("") until the closing quote.
    - Empty cells and empty rows are kept exactly where they are.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Spreadsheet apps terminate the copied range with at most one newline - that
    # terminator is not a row. Only one is removed so genuinely blank trailing rows survive.
    if text.endswith("\n"):
        text = text[:-1]

    records: list[list[str]] = []
    row: list[str] = []
    cell: list[str] = []
    i, n = 0, len(text)
    at_cell_start = True
    while i < n:
        ch = text[i]
        if at_cell_start and ch == '"':
            # Quoted cell. Find the closing quote, honouring "" escapes.
            j = i + 1
            buf: list[str] = []
            closed = False
            while j < n:
                if text[j] == '"':
                    if j + 1 < n and text[j + 1] == '"':
                        buf.append('"')
                        j += 2
                        continue
                    closed = True
                    j += 1
                    break
                buf.append(text[j])
                j += 1
            if closed and (j >= n or text[j] in "\t\n"):
                cell.extend(buf)
                i = j
                at_cell_start = False
                continue
            # Not a well-formed quoted cell (e.g. a value that merely starts with a quote): treat literally.
            cell.append(ch)
            i += 1
            at_cell_start = False
            continue
        if ch == "\t":
            row.append("".join(cell))
            cell = []
            at_cell_start = True
        elif ch == "\n":
            row.append("".join(cell))
            records.append(row)
            row, cell = [], []
            at_cell_start = True
        else:
            cell.append(ch)
            at_cell_start = False
        i += 1
    row.append("".join(cell))
    records.append(row)
    return records


def _rectangularize(records: list[list[str]], *, drop_trailing_empty_rows: bool) -> Grid:
    rows = [[_clean_cell(c) for c in r] for r in records]
    dropped = 0
    if drop_trailing_empty_rows:
        while rows and all(c == "" for c in rows[-1]):
            rows.pop()
            dropped += 1
    width = max((len(r) for r in rows), default=0)
    # Trim columns that are empty in every row at the right edge (selection overshoot).
    while width > 0 and all((len(r) < width or r[width - 1] == "") for r in rows):
        width -= 1
    # Pad short rows: spreadsheets omit trailing empty cells, the cells still exist positionally.
    rows = [(r + [""] * (width - len(r)))[:width] for r in rows]
    return Grid(rows=rows, width=width, trailing_empty_rows_dropped=dropped)


def parse_table_text(text: str) -> Grid:
    """Parse a full copied range (rows x columns)."""
    if not text or not text.strip():
        raise AppError("Nothing was pasted. Copy a range from Google Sheets or Excel and paste it here.", code="EMPTY_PASTE")
    return _rectangularize(_split_records(text), drop_trailing_empty_rows=True)


def parse_column_text(text: str) -> tuple[list[str], list[str]]:
    """Parse one pasted column. Returns (values, notes).

    Blank values inside the column are preserved so row alignment holds. If the
    paste unexpectedly contains several columns, only the first is used and a
    note is returned so the UI can tell the admin.
    """
    if text is None or text == "":
        raise AppError("Nothing was pasted. Copy a single column from your sheet and paste it here.", code="EMPTY_PASTE")
    records = _split_records(text)
    notes: list[str] = []
    if any(len(r) > 1 and any(c.strip() for c in r[1:]) for r in records):
        notes.append("The paste contained more than one column. Only the first column was used.")
    values = [_clean_cell(r[0]) if r else "" for r in records]
    if all(v == "" for v in values):
        raise AppError("The pasted column is empty.", code="EMPTY_PASTE")
    return values, notes


# --------------------------------------------------------------------------- files

def _cell_to_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.time() == time(0, 0):
            return value.date().isoformat()
        if value.date() == date(1899, 12, 30):  # Excel time-only cell
            return value.strftime("%H:%M")
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    return str(value)


def list_xlsx_sheets(content: bytes) -> list[str]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(content), read_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def parse_xlsx(content: bytes, sheet_name: str | None = None, *, fill_merged: bool = True) -> tuple[Grid, list[str], str]:
    """Read an .xlsx sheet into a Grid via OpenPyXL + Pandas.

    Merged cells are expanded to every cell they visually cover (a merged "Unit 1"
    spanning 10 rows means all 10 lectures are Unit 1); a note records it.
    """
    import pandas as pd
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception:
        raise AppError("This file could not be read as an Excel workbook (.xlsx).", code="INVALID_SPREADSHEET")
    sheets = list(wb.sheetnames)
    name = sheet_name or sheets[0]
    if name not in sheets:
        raise AppError(f"Sheet '{name}' was not found in the workbook.", code="SHEET_NOT_FOUND", details={"sheets": sheets})
    ws = wb[name]

    matrix = [[_cell_to_str(c) for c in row] for row in ws.iter_rows(values_only=True)]
    notes: list[str] = []
    if fill_merged and ws.merged_cells.ranges:
        expanded = 0
        for rng in ws.merged_cells.ranges:
            top_left = matrix[rng.min_row - 1][rng.min_col - 1] if rng.min_row - 1 < len(matrix) else ""
            for r in range(rng.min_row - 1, min(rng.max_row, len(matrix))):
                for c in range(rng.min_col - 1, min(rng.max_col, len(matrix[r]))):
                    if (r, c) != (rng.min_row - 1, rng.min_col - 1):
                        matrix[r][c] = top_left
                        expanded += 1
        if expanded:
            notes.append(f"{len(ws.merged_cells.ranges)} merged cell range(s) were expanded so every covered row keeps its value.")
    wb.close()

    # Pandas gives us a uniform frame to trim fully-empty leading/trailing rows and columns.
    frame = pd.DataFrame(matrix).fillna("").astype(str)
    grid = _rectangularize(frame.values.tolist(), drop_trailing_empty_rows=True)
    # Leading fully-empty rows (title spacing above the table) carry no data.
    while grid.rows and all(c == "" for c in grid.rows[0]):
        grid.rows.pop(0)
        notes.append("Empty rows above the table were skipped.")
    grid.notes.extend(dict.fromkeys(notes))
    return grid, sheets, name


def parse_csv(content: bytes) -> Grid:
    import pandas as pd

    text = None
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None or not text.strip():
        raise AppError("The CSV file is empty or uses an unsupported text encoding.", code="INVALID_SPREADSHEET")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        sep = dialect.delimiter
    except csv.Error:
        sep = ","
    try:
        frame = pd.read_csv(io.StringIO(text), sep=sep, header=None, dtype=str, keep_default_na=False,
                            skip_blank_lines=False, engine="python")
    except Exception:
        raise AppError("This CSV file could not be parsed. Check that it is a plain comma-separated file.", code="INVALID_SPREADSHEET")
    return _rectangularize(frame.fillna("").values.tolist(), drop_trailing_empty_rows=True)


def column_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters
