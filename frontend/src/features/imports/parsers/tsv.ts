/**
 * Spreadsheet clipboard parser (Google Sheets / Excel -> rows x columns).
 *
 * Mirrors app/services/import_parsing.py so the admin sees the same row and
 * column counts the server will use. Rules:
 *   - "\t" separates cells; "\n", "\r\n" or "\r" separate rows
 *   - a cell starting with a double quote may contain tabs/newlines and "" escapes
 *   - exactly one trailing line terminator is dropped (it is not a row)
 *   - empty cells and empty rows keep their position - nothing shifts
 *   - only surrounding whitespace in a cell is trimmed
 */

export type ParsedGrid = { rows: string[][]; width: number; trailingEmptyRowsDropped: number }

const clean = (v: string) => v.replace(/ /g, ' ').replace(/\r\n?/g, '\n').trim()

export function splitRecords(input: string): string[][] {
  let text = input.replace(/\r\n?/g, '\n')
  if (text.endsWith('\n')) text = text.slice(0, -1)
  const records: string[][] = []
  let row: string[] = []
  let cell = ''
  let atStart = true
  let i = 0
  const n = text.length
  while (i < n) {
    const ch = text[i]
    if (atStart && ch === '"') {
      let j = i + 1
      let buf = ''
      let closed = false
      while (j < n) {
        if (text[j] === '"') {
          if (text[j + 1] === '"') {
            buf += '"'
            j += 2
            continue
          }
          closed = true
          j += 1
          break
        }
        buf += text[j]
        j += 1
      }
      if (closed && (j >= n || text[j] === '\t' || text[j] === '\n')) {
        cell += buf
        i = j
        atStart = false
        continue
      }
      cell += ch
      i += 1
      atStart = false
      continue
    }
    if (ch === '\t') {
      row.push(cell)
      cell = ''
      atStart = true
    } else if (ch === '\n') {
      row.push(cell)
      records.push(row)
      row = []
      cell = ''
      atStart = true
    } else {
      cell += ch
      atStart = false
    }
    i += 1
  }
  row.push(cell)
  records.push(row)
  return records
}

export function parseTable(text: string): ParsedGrid {
  let rows = splitRecords(text).map((r) => r.map(clean))
  let dropped = 0
  while (rows.length && rows[rows.length - 1].every((c) => c === '')) {
    rows.pop()
    dropped += 1
  }
  let width = Math.max(0, ...rows.map((r) => r.length))
  while (width > 0 && rows.every((r) => r.length < width || r[width - 1] === '')) width -= 1
  rows = rows.map((r) => [...r, ...Array(Math.max(0, width - r.length)).fill('')].slice(0, width))
  return { rows, width, trailingEmptyRowsDropped: dropped }
}

export function parseColumn(text: string): { values: string[]; multipleColumns: boolean } {
  const records = splitRecords(text)
  return {
    values: records.map((r) => clean(r[0] ?? '')),
    multipleColumns: records.some((r) => r.length > 1 && r.slice(1).some((c) => c.trim() !== '')),
  }
}

export function columnLetter(index: number): string {
  let s = ''
  let n = index + 1
  while (n) {
    const rem = (n - 1) % 26
    s = String.fromCharCode(65 + rem) + s
    n = Math.floor((n - 1) / 26)
  }
  return s
}
