// DataTable: tabla reutilizable con buscador, filtros (slot), paginación,
// estado carga/esqueletos y estado vacío diferenciado. Genérica sobre filas T.
//
// Uso previsto: listados admin (normas, segmentos, usuarios). El slot
// `filtros` queda a cargo del caller (selects de norma/tipo, etc.). Estados
// de carga y vacío incorporados para no duplicarlos en cada página.

import type { ReactNode } from "react";

import "./DataTable.css";

export interface DataTableColumn<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
}

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  rows: T[] | null;
  /** Devuelve la key estable de una fila (ej. `(r) => r.id`). */
  rowKey: (row: T) => string | number;
  /** Slot con controles de filtrado que se renderiza a la izquierda del buscador. */
  filtros?: ReactNode;
  searchPlaceholder?: string;
  searchValue?: string;
  onSearchChange?: (v: string) => void;
  emptyMessage: string;
  /** Antepone columna "#" con número de fila global ((page-1)*size + i + 1)
   *  en vez del id de BD (salta con soft-deletes). Default false. */
  numerada?: boolean;
  /** total de filas (para calcular páginas). null → oculta paginación. */
  total?: number | null;
  page?: number;
  pageSize?: number;
  onPageChange?: (page: number) => void;
}

export default function DataTable<T>({
  columns,
  rows,
  rowKey,
  filtros,
  searchPlaceholder = "Buscar...",
  searchValue,
  onSearchChange,
  emptyMessage,
  numerada = false,
  total = null,
  page = 1,
  pageSize = 10,
  onPageChange,
}: DataTableProps<T>) {
  const loading = rows === null;
  const totalPages =
    total !== null ? Math.max(1, Math.ceil(total / pageSize)) : 1;
  const noMore = onPageChange === undefined;
  const searchable = onSearchChange !== undefined;

  return (
    <div className="datatable">
      {(filtros !== undefined || searchable) && (
        <div className="datatable__toolbar">
          {filtros !== undefined ? (
            <div className="datatable__filtros">{filtros}</div>
          ) : null}
          {searchable && (
            <input
              type="search"
              value={searchValue}
              placeholder={searchPlaceholder}
              aria-label={searchPlaceholder.replace("...", "")}
              onChange={(e) => onSearchChange?.(e.target.value)}
              className="datatable__search"
            />
          )}
        </div>
      )}

      <div className="datatable__table-wrap">
        <table className="datatable__table">
          <thead>
            <tr>
              {numerada && <th className="datatable__num-header">#</th>}
              {columns.map((c) => (
                <th key={c.key}>{c.header}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading &&
              Array.from({ length: 3 }).map((_, i) => (
                <tr key={`skeleton-${i}`}>
                  {numerada && <td />}
                  {columns.map((c) => (
                    <td key={c.key}>
                      <span className="datatable__skeleton" />
                    </td>
                  ))}
                </tr>
              ))}
            {!loading && rows.length === 0 && (
              <tr>
                <td
                  colSpan={columns.length + (numerada ? 1 : 0)}
                  className="datatable__empty"
                >
                  {emptyMessage}
                </td>
              </tr>
            )}
            {!loading &&
              rows.map((r, i) => (
                <tr key={rowKey(r)}>
                  {numerada && (
                    <td className="datatable__num">
                      {(page - 1) * pageSize + i + 1}
                    </td>
                  )}
                  {columns.map((c) => (
                    <td key={c.key}>
                      {c.render
                        ? c.render(r)
                        : String((r as Record<string, unknown>)[c.key] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {total !== null && total > pageSize && (
        <nav className="datatable__pagination" aria-label="Paginación">
          <button
            type="button"
            onClick={() => onPageChange?.(page - 1)}
            disabled={page <= 1 || noMore}
            className="datatable__page-btn"
          >
            ← Ant
          </button>
          <span className="datatable__page-info">
            Página {page} de {totalPages}
          </span>
          <button
            type="button"
            onClick={() => onPageChange?.(page + 1)}
            disabled={page >= totalPages || noMore}
            className="datatable__page-btn"
          >
            Sig →
          </button>
        </nav>
      )}
    </div>
  );
}
