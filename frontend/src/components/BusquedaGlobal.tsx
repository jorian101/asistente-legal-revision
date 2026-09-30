// BusquedaGlobal: paleta Ctrl/Cmd+K del TopBar. Grupos según el rol:
// - Todos: "Ir a" (solo las páginas que el menú ya muestra para ese rol).
// - Asistente: conversaciones propias (chatStore local) y fuentes visibles
//   (/fuentes ya viene filtrado por visibilidad en el servidor, Regla 4).
// ponytail: filtra en cliente; usuarios/corpus para admin necesitan un
// endpoint de búsqueda server-side y quedan fuera.

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { useNavigate } from "react-router-dom";
import { FileText, History, Search } from "lucide-react";

import {
  CATEGORIA_LABEL,
  listarFuentes,
  type CategoriaFuente,
  type FuenteDTO,
} from "../api/fuentes";
import { chatStore } from "../lib/chatStore";
import type { Modulo } from "../config/modulosPorRol";

import styles from "./BusquedaGlobal.module.css";

interface Props {
  open: boolean;
  onClose: () => void;
  paginas: Modulo[];
  /** null: sin conversaciones (área admin). */
  usuarioId: number | null;
  conFuentes: boolean;
}

interface Resultado {
  id: string;
  grupo: string;
  titulo: string;
  detalle?: string;
  to: string;
  icono: Modulo["icono"];
}

const CATEGORIAS: CategoriaFuente[] = ["norma", "jurisprudencia", "doctrina"];
const MAX_POR_GRUPO = 6;

const normalizar = (s: string) =>
  s
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();

export function BusquedaGlobal({
  open,
  onClose,
  paginas,
  usuarioId,
  conFuentes,
}: Props) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [activo, setActivo] = useState(0);
  const [fuentes, setFuentes] = useState<FuenteDTO[] | null>(null);
  const [errorFuentes, setErrorFuentes] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActivo(0);
    inputRef.current?.focus();
  }, [open]);

  // Las fuentes se piden al abrir por primera vez y quedan para la sesión.
  useEffect(() => {
    if (!open || !conFuentes || fuentes !== null) return;
    Promise.all(CATEGORIAS.map(listarFuentes))
      .then((listas) => setFuentes(listas.flat()))
      .catch(() => setErrorFuentes(true));
  }, [open, conFuentes, fuentes]);

  const resultados = useMemo<Resultado[]>(() => {
    const q = normalizar(query.trim());
    const coincide = (texto: string) => normalizar(texto).includes(q);

    const irA = paginas
      .filter((p) => coincide(p.label))
      .map((p) => ({
        id: `p:${p.to}`,
        grupo: "Ir a",
        titulo: p.label,
        detalle: p.descripcion,
        to: p.to,
        icono: p.icono,
      }));

    const conversaciones =
      usuarioId === null
        ? []
        : (q
            ? chatStore.buscarConversaciones(usuarioId, query)
            : chatStore.listarConversaciones(usuarioId)
          )
            .slice(0, MAX_POR_GRUPO)
            .map((c) => ({
              id: `c:${c.id}`,
              grupo: "Conversaciones",
              titulo: c.titulo,
              to: `/asistente/consultar?chat=${c.id}`,
              icono: History,
            }));

    const deFuentes = q
      ? (fuentes ?? [])
          .filter((f) => coincide(`${f.nombre} ${f.abreviatura}`))
          .slice(0, MAX_POR_GRUPO)
          .map((f) => ({
            id: `f:${f.id}`,
            grupo: "Fuentes",
            titulo: f.nombre,
            detalle: `${CATEGORIA_LABEL[f.categoria]} · ${f.abreviatura}`,
            to: `/asistente/doctrina?categoria=${f.categoria}`,
            icono: FileText,
          }))
      : [];

    return [...irA.slice(0, MAX_POR_GRUPO), ...conversaciones, ...deFuentes];
  }, [query, paginas, usuarioId, fuentes]);

  if (!open) return null;

  const elegir = (r: Resultado) => {
    onClose();
    navigate(r.to);
  };

  const alTeclear = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const paso = e.key === "ArrowDown" ? 1 : -1;
      setActivo((i) =>
        resultados.length === 0
          ? 0
          : (i + paso + resultados.length) % resultados.length,
      );
    } else if (e.key === "Enter" && resultados[activo]) {
      e.preventDefault();
      elegir(resultados[activo]);
    }
  };

  const cargandoFuentes =
    conFuentes && fuentes === null && !errorFuentes && query.trim() !== "";

  return (
    <div className={styles.backdrop} onClick={onClose}>
      <div
        className={styles.paleta}
        role="dialog"
        aria-modal="true"
        aria-label="Búsqueda global"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={alTeclear}
      >
        <div className={styles.campo}>
          <Search size={18} aria-hidden="true" />
          <input
            ref={inputRef}
            className={styles.input}
            placeholder={
              conFuentes
                ? "Buscar páginas, conversaciones o fuentes…"
                : "Buscar páginas…"
            }
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActivo(0);
            }}
            role="combobox"
            aria-expanded="true"
            aria-controls="busqueda-global-lista"
            aria-activedescendant={
              resultados[activo] ? `bg-${resultados[activo].id}` : undefined
            }
          />
          <kbd className={styles.esc}>Esc</kbd>
        </div>
        <ul
          id="busqueda-global-lista"
          className={styles.lista}
          role="listbox"
          aria-label="Resultados"
        >
          {resultados.map((r, i) => {
            const Icono = r.icono;
            const nuevoGrupo = i === 0 || resultados[i - 1].grupo !== r.grupo;
            return (
              <li key={r.id} role="presentation">
                {nuevoGrupo && (
                  <div className={styles.grupo} role="presentation">
                    {r.grupo}
                  </div>
                )}
                <div
                  id={`bg-${r.id}`}
                  role="option"
                  aria-selected={i === activo}
                  className={styles.item}
                  onMouseMove={() => setActivo(i)}
                  onClick={() => elegir(r)}
                >
                  {Icono && <Icono size={16} aria-hidden="true" />}
                  <span className={styles.titulo}>{r.titulo}</span>
                  {r.detalle && (
                    <span className={styles.detalle}>{r.detalle}</span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
        {resultados.length === 0 && !cargandoFuentes && (
          <p className={styles.estado} role="status">
            Sin resultados para «{query.trim()}».
          </p>
        )}
        {cargandoFuentes && (
          <p className={styles.estado} role="status">
            Buscando en las fuentes…
          </p>
        )}
        {errorFuentes && query.trim() !== "" && (
          <p className={styles.estado} role="alert">
            No se pudieron cargar las fuentes; se muestran solo páginas y
            conversaciones.
          </p>
        )}
      </div>
    </div>
  );
}
