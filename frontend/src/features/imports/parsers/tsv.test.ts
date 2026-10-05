import { describe, expect, it } from 'vitest'
import { columnLetter, parseColumn, parseTable } from './tsv'

describe('parseTable', () => {
  it('splits rows and columns from a Sheets copy', () => {
    const g = parseTable('SrNo\tLecture_No\tTopic\n1\t1\tRecursion\n2\t2\tMaster Theorem\n')
    expect(g.width).toBe(3)
    expect(g.rows).toHaveLength(3)
    expect(g.rows[2]).toEqual(['2', '2', 'Master Theorem'])
  })

  it('normalises CRLF', () => {
    expect(parseTable('a\tb\r\n1\t2\r\n').rows).toEqual([['a', 'b'], ['1', '2']])
  })

  it('keeps blank cells in place and pads short rows', () => {
    expect(parseTable('A\tB\tC\n1\t\t3\n4').rows).toEqual([['A', 'B', 'C'], ['1', '', '3'], ['4', '', '']])
  })

  it('keeps a leading empty cell (no column shift)', () => {
    expect(parseTable('\tB\nx\ty').rows).toEqual([['', 'B'], ['x', 'y']])
  })

  it('preserves blank rows inside the data and drops trailing ones', () => {
    const g = parseTable('A\n1\n\n3\n\n\n')
    expect(g.rows).toEqual([['A'], ['1'], [''], ['3']])
    expect(g.trailingEmptyRowsDropped).toBe(2)
  })

  it('handles quoted multi-line cells', () => {
    const g = parseTable('Topic\tSubs\nQuick Sort\t"Lomuto\nHoare"\n')
    expect(g.rows[1]).toEqual(['Quick Sort', 'Lomuto\nHoare'])
  })
})

describe('parseColumn', () => {
  it('preserves blank values for row alignment', () => {
    expect(parseColumn('K1\n\nK3\n').values).toEqual(['K1', '', 'K3'])
  })
  it('flags multi-column pastes', () => {
    expect(parseColumn('a\tb\nc\td').multipleColumns).toBe(true)
  })
})

it('column letters', () => {
  expect([0, 25, 26, 27].map(columnLetter)).toEqual(['A', 'Z', 'AA', 'AB'])
})
