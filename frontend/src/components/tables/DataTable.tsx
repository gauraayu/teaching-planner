import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type Row,
  type SortingState,
  type VisibilityState,
} from '@tanstack/react-table'
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsUpDown, Columns3, Search } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { EmptyState, ErrorState, LoadingRows } from '@/components/feedback/States'
import { Button } from '@/components/ui/Button'
import { Menu } from '@/components/ui/Menu'
import { cn } from '@/utils/cn'

declare module '@tanstack/react-table' {
  interface ColumnMeta<TData, TValue> {
    className?: string
    headerClassName?: string
    align?: 'left' | 'right' | 'center'
    _?: [TData, TValue]
  }
}

export type DataTableProps<T> = {
  columns: ColumnDef<T, any>[]
  data: T[] | undefined
  loading?: boolean
  error?: string | null
  onRetry?: () => void
  searchable?: boolean
  searchPlaceholder?: string
  toolbar?: ReactNode
  empty?: ReactNode
  pageSize?: number
  onRowClick?: (row: T) => void
  rowClassName?: (row: Row<T>) => string | undefined
  initialSorting?: SortingState
  initialHidden?: VisibilityState
  columnToggle?: boolean
  stickyHeader?: boolean
  maxHeight?: string
  dense?: boolean
  caption?: string
}

/** Compact enterprise table: sort, search, paginate, column visibility, loading/empty/error states. */
export function DataTable<T>({
  columns,
  data,
  loading,
  error,
  onRetry,
  searchable = true,
  searchPlaceholder = 'Search…',
  toolbar,
  empty,
  pageSize = 25,
  onRowClick,
  rowClassName,
  initialSorting = [],
  initialHidden = {},
  columnToggle = false,
  stickyHeader = true,
  maxHeight,
  dense,
  caption,
}: DataTableProps<T>) {
  const [sorting, setSorting] = useState<SortingState>(initialSorting)
  const [globalFilter, setGlobalFilter] = useState('')
  const [visibility, setVisibility] = useState<VisibilityState>(initialHidden)
  const table = useReactTable({
    data: data ?? [],
    columns,
    state: { sorting, globalFilter, columnVisibility: visibility },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    onColumnVisibilityChange: setVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize } },
    autoResetPageIndex: false,
  })
  const rows = table.getRowModel().rows
  const filteredCount = table.getFilteredRowModel().rows.length
  const { pageIndex } = table.getState().pagination
  const showToolbar = searchable || toolbar || columnToggle

  return (
    <div className="flex min-w-0 flex-col">
      {showToolbar && (
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2.5">
          {searchable && (
            <div className="relative w-full sm:w-64">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-fg-muted" aria-hidden />
              <input
                type="search"
                value={globalFilter}
                onChange={(e) => {
                  setGlobalFilter(e.target.value)
                  table.setPageIndex(0)
                }}
                placeholder={searchPlaceholder}
                aria-label={searchPlaceholder}
                className="field h-8 pl-8 text-[13px]"
              />
            </div>
          )}
          {toolbar}
          {columnToggle && (
            <div className="ml-auto">
              <Menu
                label="Visible columns"
                trigger={(p) => (
                  <Button size="sm" variant="ghost" icon={<Columns3 className="h-3.5 w-3.5" />} {...p}>
                    Columns
                  </Button>
                )}
                items={table
                  .getAllLeafColumns()
                  .filter((c) => c.getCanHide())
                  .map((c) => ({
                    label: (
                      <span className="flex items-center gap-2">
                        <input type="checkbox" readOnly checked={c.getIsVisible()} className="accent-primary" />
                        {typeof c.columnDef.header === 'string' ? c.columnDef.header : c.id}
                      </span>
                    ),
                    onSelect: () => c.toggleVisibility(),
                  }))}
              />
            </div>
          )}
        </div>
      )}
      {error ? (
        <ErrorState message={error} onRetry={onRetry} />
      ) : loading && !data ? (
        <LoadingRows />
      ) : (
        <div className={cn('overflow-auto scroll-thin', maxHeight)}>
          <table className="w-full border-collapse text-left text-[13px]">
            {caption && <caption className="sr-only">{caption}</caption>}
            <thead className={cn(stickyHeader && 'sticky top-0 z-10')}>
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id} className="border-b border-line bg-surface-2">
                  {hg.headers.map((h) => {
                    const sortable = h.column.getCanSort()
                    const sorted = h.column.getIsSorted()
                    const meta = h.column.columnDef.meta
                    return (
                      <th
                        key={h.id}
                        scope="col"
                        aria-sort={sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : undefined}
                        className={cn(
                          'h-9 px-3 text-[11.5px] font-semibold tracking-wide whitespace-nowrap text-fg-label uppercase',
                          meta?.align === 'right' && 'text-right',
                          meta?.headerClassName,
                        )}
                      >
                        {h.isPlaceholder ? null : sortable ? (
                          <button
                            type="button"
                            onClick={h.column.getToggleSortingHandler()}
                            className={cn('inline-flex items-center gap-1 uppercase hover:text-fg', meta?.align === 'right' && 'flex-row-reverse')}
                          >
                            {flexRender(h.column.columnDef.header, h.getContext())}
                            {sorted === 'asc' ? <ArrowUp className="h-3 w-3" /> : sorted === 'desc' ? <ArrowDown className="h-3 w-3" /> : <ChevronsUpDown className="h-3 w-3 opacity-40" />}
                          </button>
                        ) : (
                          flexRender(h.column.columnDef.header, h.getContext())
                        )}
                      </th>
                    )
                  })}
                </tr>
              ))}
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.id}
                  onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                  onKeyDown={onRowClick ? (e) => e.key === 'Enter' && e.target === e.currentTarget && onRowClick(row.original) : undefined}
                  tabIndex={onRowClick ? 0 : undefined}
                  className={cn('border-b border-line-subtle last:border-0 hover:bg-surface-2/70', onRowClick && 'cursor-pointer', rowClassName?.(row))}
                >
                  {row.getVisibleCells().map((cell) => {
                    const meta = cell.column.columnDef.meta
                    return (
                      <td key={cell.id} className={cn('px-3 align-middle text-fg-soft', dense ? 'py-1.5' : 'py-2.5', meta?.align === 'right' && 'text-right', meta?.className)}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && (empty ?? <EmptyState title={globalFilter ? 'No matching records' : 'Nothing here yet'} description={globalFilter ? 'Try a different search term.' : undefined} />)}
        </div>
      )}
      {!error && filteredCount > table.getState().pagination.pageSize && (
        <div className="flex items-center justify-between gap-3 border-t border-line px-3 py-2 text-[12.5px] text-fg-label">
          <span className="tnum">
            {pageIndex * table.getState().pagination.pageSize + 1}–{Math.min((pageIndex + 1) * table.getState().pagination.pageSize, filteredCount)} of {filteredCount}
          </span>
          <div className="flex items-center gap-1">
            <Button size="icon" variant="ghost" aria-label="Previous page" disabled={!table.getCanPreviousPage()} onClick={() => table.previousPage()}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="tnum px-1">
              Page {pageIndex + 1} of {table.getPageCount()}
            </span>
            <Button size="icon" variant="ghost" aria-label="Next page" disabled={!table.getCanNextPage()} onClick={() => table.nextPage()}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
