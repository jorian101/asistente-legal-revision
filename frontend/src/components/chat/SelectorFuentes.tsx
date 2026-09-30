// SelectorFuentes: modal común del chat para fijar normas, jurisprudencia o doctrina
// a la consulta o al expediente. Sustituye a DoctrinaModal y JurisprudenciaModal.
// Arriba: contador, buscador y filtro (Globales/Mías, o TCP/CIDH en jurisprudencia).
// Secciones: recomendadas para el expediente (de esa categoría) y el catálogo en
// filas densas. Cada fila alterna Fijar / Fijada (click en Fijada la quita).
// El catálogo de cada categoría se muestra al reabrir y se revalida en segundo plano.

import { useEffect, useMemo, useState } from "react";
import { Check, Search } from "lucide-react";

import {
  listarRecomendadasExpediente,
  type RecomendacionDTO,
} from "../../api/doctrina";
import {
  CATEGORIA_LABEL,
  SUBGRUPO_LABEL,
  listarFuentes,
  seleccionarFuente,
  type CategoriaFuente,
  type FuenteDTO,
} from "../../api/fuentes";
import { mensajeError } from "../../lib/errors";
import { toast } from "../../lib/toasts";
import { Badge, Button, Modal, StateMessage } from "../ui";

import styles from "./SelectorFuentes.module.css";

interface Props {
  abierto: boolean;
  categoria: CategoriaFuente;
  expedienteId: number | null;
  onCerrar: () => void;
  onSeleccionada?: (abreviatura: string) => void;
  /** Abreviaturas ya fijadas en la conversación. */
  fijadas?: string[];
  onDesfijar?: (abreviatura: string) => void;
}

type Filtro = "todas" | string;

const HINT: Record<CategoriaFuente, string> = {
  norma:
    "El corpus jurídico ya se busca siempre en cada consulta. Fijá una norma puntual solo si querés forzarla en el contexto (poco común — útil si el buscador no la trae por su cuenta).",
  jurisprudencia: "Sentencias del TCP y de la Corte IDH que quieras priorizar.",
  doctrina: "Libros de doctrina que quieras priorizar.",
};

const SINGULAR: Record<CategoriaFuente, [string, string]> = {
  norma: ["norma", "normas"],
  jurisprudencia: ["sentencia", "sentencias"],
  doctrina: ["libro", "libros"],
};

const normalizar = (s: string) =>
  s
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();

export function SelectorFuentes({
  abierto,
  categoria,
  expedienteId,
  onCerrar,
  onSeleccionada,
  fijadas = [],
  onDesfijar,
}: Props) {
  const [catalogo, setCatalogo] = useState<
    Partial<Record<CategoriaFuente, FuenteDTO[]>>
  >({});
  const [recomendadas, setRecomendadas] = useState<RecomendacionDTO[]>([]);
  const [fijando, setFijando] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filtro, setFiltro] = useState<Filtro>("todas");

  useEffect(() => {
    if (!abierto) return;
    setQuery("");
    setFiltro("todas");
    listarFuentes(categoria)
      .then((lista) => setCatalogo((c) => ({ ...c, [categoria]: lista })))
      .catch((err) => {
        setCatalogo((c) => ({ ...c, [categoria]: c[categoria] ?? [] }));
        toast(mensajeError(err, "No se pudieron cargar las fuentes"), "error");
      });
    if (expedienteId !== null) {
      listarRecomendadasExpediente(expedienteId)
        .then((r) => setRecomendadas(r.filter((x) => x.corpus === categoria)))
        .catch(() => setRecomendadas([]));
    } else {
      setRecomendadas([]);
    }
  }, [abierto, categoria, expedienteId]);

  const fuentes = catalogo[categoria] ?? null;
  const esJuris = categoria === "jurisprudencia";

  const grupos = useMemo(() => {
    const q = normalizar(query.trim());
    const visibles = (fuentes ?? []).filter(
      (f) => !q || normalizar(`${f.nombre} ${f.abreviatura}`).includes(q),
    );
    const todos: { clave: string; titulo: string; items: FuenteDTO[] }[] =
      esJuris
        ? (["tcp", "cidh"] as const).map((g) => ({
            clave: g,
            titulo: SUBGRUPO_LABEL[g],
            items: visibles.filter((f) => f.subgrupo === g),
          }))
        : [
            {
              clave: "globales",
              titulo: "Globales",
              items: visibles.filter((f) => !f.es_propia),
            },
            {
              clave: "mias",
              titulo: "Mis fuentes",
              items: visibles.filter((f) => f.es_propia),
            },
          ];
    return filtro === "todas" ? todos : todos.filter((g) => g.clave === filtro);
  }, [fuentes, query, filtro, esJuris]);

  async function fijar(f: FuenteDTO) {
    setFijando(f.abreviatura);
    try {
      await seleccionarFuente(f.id, expedienteId);
      toast(
        expedienteId
          ? `${f.nombre} fijada a este expediente`
          : `${f.nombre} agregada a la consulta`,
        "success",
      );
      onSeleccionada?.(f.abreviatura);
    } catch (err) {
      toast(mensajeError(err, "No se pudo fijar la fuente"), "error");
    } finally {
      setFijando(null);
    }
  }

  const porAbreviatura = new Map(
    (fuentes ?? []).map((f) => [f.abreviatura, f]),
  );
  const [uno, varios] = SINGULAR[categoria];
  const total = fuentes?.length ?? 0;
  const nFijadas = (fuentes ?? []).filter((f) =>
    fijadas.includes(f.abreviatura),
  ).length;
  const sinCoincidencias =
    fuentes !== null && total > 0 && grupos.every((g) => g.items.length === 0);

  const accion = (f: FuenteDTO) =>
    fijadas.includes(f.abreviatura) ? (
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onDesfijar?.(f.abreviatura)}
        disabled={!onDesfijar}
        aria-label={`Quitar ${f.nombre}`}
        title="Quitar de la consulta"
      >
        <Check aria-hidden="true" />
        Fijada
      </Button>
    ) : (
      <Button
        variant="secondary"
        size="sm"
        loading={fijando === f.abreviatura}
        onClick={() => void fijar(f)}
      >
        Fijar
      </Button>
    );

  const fila = (f: FuenteDTO) => (
    <li key={f.id} className={styles.fila}>
      <div className={styles.filaTexto}>
        <span className={styles.nombre} title={f.nombre}>
          {f.nombre}
        </span>
        <span className={styles.meta}>
          {f.abreviatura}
          {f.estado_visibilidad === "pendiente" ? (
            <Badge tone="warning">En revisión</Badge>
          ) : (
            f.estado_visibilidad !== "global" && (
              <Badge tone="neutral">Privada</Badge>
            )
          )}
        </span>
      </div>
      {accion(f)}
    </li>
  );

  const filtros: [Filtro, string][] = esJuris
    ? [
        ["todas", "Todas"],
        ["tcp", "TCP"],
        ["cidh", "Corte IDH"],
      ]
    : [
        ["todas", "Todas"],
        ["globales", "Globales"],
        ["mias", "Mías"],
      ];

  return (
    <Modal
      open={abierto}
      title={CATEGORIA_LABEL[categoria]}
      subtitle={
        fuentes === null
          ? "Cargando catálogo…"
          : `${total} ${total === 1 ? uno : varios}${nFijadas ? ` · ${nFijadas} fijada${nFijadas === 1 ? "" : "s"}` : ""}`
      }
      onClose={onCerrar}
      size="md"
      footer={<Button onClick={onCerrar}>Listo</Button>}
    >
      {categoria === "norma" ? (
        <details className={styles.ayuda}>
          <summary>¿Cuándo conviene fijar una norma?</summary>
          <p>{HINT.norma}</p>
        </details>
      ) : (
        <p className={styles.hint}>{HINT[categoria]}</p>
      )}

      <div className={styles.barra}>
        <label className={styles.buscar}>
          <Search size={16} aria-hidden="true" />
          <input
            type="search"
            className="input"
            placeholder={`Buscar ${varios}…`}
            aria-label={`Buscar ${varios}`}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <div
          className={styles.segmentado}
          role="radiogroup"
          aria-label="Filtrar"
        >
          {filtros.map(([valor, texto]) => (
            <button
              key={valor}
              type="button"
              role="radio"
              aria-checked={filtro === valor}
              className={styles.segmento}
              onClick={() => setFiltro(valor)}
            >
              {texto}
            </button>
          ))}
        </div>
      </div>

      {expedienteId !== null && recomendadas.length > 0 && !query && (
        <section className={styles.recomendadas}>
          <h3 className={styles.grupoTitulo}>
            Recomendadas para este expediente
            <span className={styles.grupoCuenta}>{recomendadas.length}</span>
          </h3>
          <ul className={styles.lista}>
            {recomendadas.map((r) => {
              const f = r.corpus_ref
                ? porAbreviatura.get(r.corpus_ref)
                : undefined;
              return f ? (
                fila(f)
              ) : (
                <li key={`r-${r.id}`} className={styles.fila}>
                  <div className={styles.filaTexto}>
                    <span className={styles.nombre}>{r.nombre_archivo}</span>
                    <span className={styles.meta}>
                      Aún no está en el catálogo
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {fuentes === null ? (
        <StateMessage tipo="cargando">Cargando {varios}…</StateMessage>
      ) : total === 0 ? (
        <StateMessage tipo="vacio">
          Todavía no hay {varios}. Podés subirlas desde la sección Fuentes.
        </StateMessage>
      ) : sinCoincidencias ? (
        <StateMessage tipo="vacio">
          Ninguna fuente coincide con «{query.trim()}».
        </StateMessage>
      ) : (
        grupos.map((g) => (
          <section key={g.clave} className={styles.grupo}>
            <h3 className={styles.grupoTitulo}>
              {g.titulo}
              <span className={styles.grupoCuenta}>{g.items.length}</span>
            </h3>
            {g.items.length === 0 ? (
              <p className={styles.vacio}>Sin fuentes.</p>
            ) : (
              <ul className={styles.lista}>{g.items.map(fila)}</ul>
            )}
          </section>
        ))
      )}
    </Modal>
  );
}
