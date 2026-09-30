// DocumentoPreview: renderiza el esqueleto de un formato TSJM como hoja.
//
// Pinta cada bloque del esqueleto (o bloques) a una hoja con tamaño
// configurable (carta/oficio/A4, default carta) y márgenes globales
// (presets o manual). Los placeholders {{VAR}} se resaltan como chips.
//
// Selección múltiple de bloques:
//   - Click en bloque: seleccionar 1 + abrir editor inline.
//   - Ctrl/Shift-click: sumar/quitar del multi-selección.
//   - Arrastre desde el gutter (columna fina a la izquierda): seleccionar
//     por rango; al soltar se muestra la toolbar flotante.
//   - Ctrl/Cmd+A: seleccionar todos los bloques.
//   El gutter es un overlay que NO altera el layout (preview fiel al Word).
//
// La edición inline de un solo bloque ocurre vía `editorSlot`.

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from "react";

import type { BloqueDTO, BloqueEsqueletoDTO } from "../../api/formatos";
import { Button } from "../../components/ui";
import { fuenteCss, normalizarFuente } from "../../lib/fuentes";
import { segmentarNegrita } from "../../lib/textoBloque";

// Sus estilos viven en Formatos.css: sin importarlo acá, fuera de la página de Formatos
// (p. ej. Obrados generados) la hoja y la barra salían sin estilo.
import "./Formatos.css";

export type TamanoHoja = "carta" | "oficio" | "a4";

export type MargenesMM = {
  top: number;
  right: number;
  bottom: number;
  left: number;
};

export type PreviewOverride = {
  texto?: string;
  align?: string;
  bold?: boolean;
  underline?: boolean;
  size_pt?: number | null;
  font?: string | null;
};

const TAMANOS_MM: Record<TamanoHoja, { width: number; height: number }> = {
  carta: { width: 216, height: 279 }, // 8.5x11 in
  oficio: { width: 216, height: 356 }, // 8.5x14 in (legal)
  a4: { width: 210, height: 297 },
};

export const MARGENES_PRESETS: Record<string, MargenesMM> = {
  Estrecho: { top: 15, right: 12, bottom: 15, left: 20 },
  Normal: { top: 25, right: 20, bottom: 20, left: 30 },
  Legal: { top: 25, right: 20, bottom: 20, left: 40 }, // margen legal boliviano
  Amplio: { top: 35, right: 30, bottom: 35, left: 50 },
};

function runsToTexto(runs: { text: string }[]): string {
  return runs.map((r) => r.text).join("");
}

/** Separa el texto en segmentos fijos y placeholders {{...}}. */
function segmentarPlaceholders(
  texto: string,
): Array<{ var: boolean; valor: string }> {
  const partes = texto.split(/(\{\{[^}]+\}\})/g);
  return partes
    .filter((p) => p.length > 0)
    .map((p) => ({ var: p.startsWith("{{") && p.endsWith("}}"), valor: p }));
}

interface BloqueRender {
  key: string;
  align: string;
  bold: boolean;
  underline: boolean;
  allcaps: boolean;
  size_pt: number | null;
  font: string | null;
  texto: string;
  template: boolean;
}

function toRenderBloque(
  b: BloqueDTO | BloqueEsqueletoDTO,
): BloqueRender | null {
  const esqueleto = b as BloqueEsqueletoDTO;
  const texto = esqueleto.texto_plantilla ?? runsToTexto(b.runs);
  if (!texto.trim()) return null;
  const primer = b.runs[0];
  return {
    key: `p${b.page}:i${b.index}`,
    align: b.align ?? "left",
    bold: primer?.bold ?? false,
    underline: primer?.underline ?? false,
    allcaps: primer?.allcaps ?? false,
    size_pt: primer?.size_pt ?? null,
    font: primer?.font ?? null,
    texto,
    template: esqueleto.template ?? false,
  };
}

// ¿El foco está en un campo de texto? Incluye el editor de bloque (contenteditable de TipTap):
// sin esto, los atajos globales le robaban Ctrl+Z (descartaba todas las ediciones), Ctrl+A y
// Backspace/Delete (no se podía borrar un carácter con el bloque seleccionado).
function esCampoDeTexto(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  if (!el?.tagName) return false;
  return (
    ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) ||
    el.isContentEditable ||
    el.closest('[contenteditable="true"]') !== null
  );
}

const TAMANOS_PX = ["", "12px", "13px", "14px", "16px", "18px", "20px", "24px"];
const FUENTES = [
  "",
  "Arial",
  "Times New Roman",
  "Georgia",
  "Courier New",
] as const;

export default function DocumentoPreview({
  bloques,
  tamano,
  onTamanoChange,
  mostrarComparador,
  comparadorActivo,
  onToggleComparador,
  overrides,
  editorSlot,
  margenes,
  onMargenesChange,
  onAbrirMargenesManual,
  onAplicarSeleccion,
  onSeleccionChange,
  editandoKey,
  onEditarBloque,
  onCerrarEdicion,
  orden,
  onReordenar,
  onEliminarSeleccion,
  onDeshacer,
  onRehacer,
  canDeshacer,
  canRehacer,
  onCancelarLocal,
  onGuardarTodo,
  hayCambios,
  saving,
  puedeEditar = true,
}: {
  bloques: Array<BloqueDTO | BloqueEsqueletoDTO>;
  tamano: TamanoHoja;
  onTamanoChange?: (t: TamanoHoja) => void;
  mostrarComparador?: boolean;
  comparadorActivo?: boolean;
  onToggleComparador?: () => void;
  overrides?: Record<string, PreviewOverride>;
  editorSlot?: ReactNode;
  margenes?: MargenesMM;
  onMargenesChange?: (m: MargenesMM) => void;
  onAbrirMargenesManual?: () => void;
  onAplicarSeleccion?: (claves: string[], cambio: PreviewOverride) => void;
  onSeleccionChange?: (claves: string[]) => void;
  editandoKey?: string | null;
  onEditarBloque?: (key: string) => void;
  onCerrarEdicion?: () => void;
  orden?: string[] | null;
  onReordenar?: (nuevoOrden: string[]) => void;
  onEliminarSeleccion?: (claves: string[]) => void;
  onDeshacer?: () => void;
  onRehacer?: () => void;
  canDeshacer?: boolean;
  canRehacer?: boolean;
  onCancelarLocal?: () => void;
  onGuardarTodo?: () => void;
  hayCambios?: boolean;
  saving?: boolean;
  /** Sin formatos.actualizar: solo lectura (sin reordenar, editar márgenes,
   * aplicar estilo por selección, eliminar ni Guardar todo). */
  puedeEditar?: boolean;
}) {
  const dims = TAMANOS_MM[tamano];
  const marg = margenes ?? MARGENES_PRESETS.Legal;
  const editando = editandoKey ?? null;

  const [seleccion, setSeleccion] = useState<Set<string>>(new Set());
  const [arrastre, setArrastre] = useState<{
    yInicio: number;
    yActual: number;
  } | null>(null);
  const [reorden, setReorden] = useState<{
    dragKey: string;
    yInicio: number;
    yActual: number;
    overKey: string | null;
    before: boolean;
  } | null>(null);
  const [toolbarPos, setToolbarPos] = useState<{
    top: number;
    left: number;
    abajo: boolean;
  } | null>(null);

  const hojaRef = useRef<HTMLDivElement | null>(null);
  const bloqueRefs = useRef<Map<string, HTMLParagraphElement>>(new Map());
  const seleccionRef = useRef<Set<string>>(new Set());
  seleccionRef.current = seleccion;

  const rendersBase = bloques
    .map(toRenderBloque)
    .filter((b): b is BloqueRender => b !== null)
    .map((b) => {
      const ov = overrides?.[b.key];
      if (!ov) return b;
      return {
        ...b,
        texto: ov.texto ?? b.texto,
        align: ov.align ?? b.align,
        bold: ov.bold ?? b.bold,
        underline: ov.underline ?? b.underline,
        size_pt: ov.size_pt ?? b.size_pt,
        font: ov.font ?? b.font,
      };
    });

  const renders = (() => {
    if (!orden || orden.length === 0) return rendersBase;
    const byKey = new Map(rendersBase.map((b) => [b.key, b] as const));
    const seen = new Set<string>();
    const ordenados: BloqueRender[] = [];
    for (const k of orden) {
      const b = byKey.get(k);
      if (b) {
        ordenados.push(b);
        seen.add(k);
      }
    }
    for (const b of rendersBase) if (!seen.has(b.key)) ordenados.push(b);
    return ordenados;
  })();

  const actualizarSeleccion = useCallback(
    (n: Set<string>) => {
      setSeleccion(n);
      onSeleccionChange?.([...n]);
    },
    [onSeleccionChange],
  );

  // Seleccionar por rango vertical (arrastre).
  const seleccionarRango = useCallback(
    (yDesde: number, yHasta: number) => {
      const hoja = hojaRef.current;
      if (!hoja) return;
      const y1 = Math.min(yDesde, yHasta);
      const y2 = Math.max(yDesde, yHasta);
      const dentro: string[] = [];
      bloqueRefs.current.forEach((el, key) => {
        const r = el.getBoundingClientRect();
        const centro = r.top + r.height / 2;
        if (centro >= y1 && centro <= y2) dentro.push(key);
      });
      actualizarSeleccion(new Set(dentro));
    },
    [actualizarSeleccion],
  );

  const posicionarToolbar = useCallback(() => {
    const hoja = hojaRef.current;
    if (!hoja) return;
    const hojaRect = hoja.getBoundingClientRect();
    const keys = [...seleccionRef.current];
    if (keys.length === 0) {
      setToolbarPos(null);
      return;
    }
    let primer: DOMRect | null = null;
    let ultimo: DOMRect | null = null;
    for (const k of keys) {
      const el = bloqueRefs.current.get(k);
      if (!el) continue;
      const r = el.getBoundingClientRect();
      if (!primer || r.top < primer.top) primer = r;
      if (!ultimo || r.bottom > ultimo.bottom) ultimo = r;
    }
    if (!primer || !ultimo) {
      setToolbarPos(null);
      return;
    }
    const viewportH = window.innerHeight;
    const primerEnViewport = primer.top >= 0 && primer.top < viewportH;
    // clamp horizontal para que la toolbar no se corte (ancho estimado 520px)
    const toolbarW = 520;
    const clampLeft = (left: number) =>
      Math.max(4, Math.min(left, hojaRect.width - toolbarW - 4));
    if (primerEnViewport) {
      setToolbarPos({
        top: primer.top - hojaRect.top,
        left: clampLeft(primer.left - hojaRect.left),
        abajo: false,
      });
    } else {
      setToolbarPos({
        top: ultimo.bottom - hojaRect.top,
        left: clampLeft(ultimo.left - hojaRect.left),
        abajo: true,
      });
    }
  }, []);

  useLayoutEffect(() => {
    posicionarToolbar();
  }, [seleccion, posicionarToolbar]);

  // Atajos: Ctrl/Cmd+A, Z/Y, Escape, Delete/Backspace.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a") {
        if (esCampoDeTexto(e.target)) return;
        e.preventDefault();
        actualizarSeleccion(new Set(renders.map((r) => r.key)));
        return;
      }
      if (
        (e.ctrlKey || e.metaKey) &&
        e.key.toLowerCase() === "z" &&
        !e.shiftKey
      ) {
        if (esCampoDeTexto(e.target)) return;
        e.preventDefault();
        onDeshacer?.();
        return;
      }
      if (
        (e.ctrlKey || e.metaKey) &&
        (e.key.toLowerCase() === "y" ||
          (e.shiftKey && e.key.toLowerCase() === "z"))
      ) {
        if (esCampoDeTexto(e.target)) return;
        e.preventDefault();
        onRehacer?.();
        return;
      }
      if (e.key === "Escape") {
        if (seleccionRef.current.size > 0) {
          e.preventDefault();
          actualizarSeleccion(new Set());
          onCerrarEdicion?.();
        }
        return;
      }
      if (
        puedeEditar &&
        (e.key === "Delete" || e.key === "Backspace") &&
        seleccionRef.current.size > 0
      ) {
        // Sin acción de borrar bloque conectada, no bloquear la tecla.
        if (esCampoDeTexto(e.target) || !onEliminarSeleccion) return;
        e.preventDefault();
        onEliminarSeleccion([...seleccionRef.current]);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    renders,
    actualizarSeleccion,
    onCerrarEdicion,
    onEliminarSeleccion,
    puedeEditar,
  ]);

  // Reposicionar toolbar en scroll/resize.
  useEffect(() => {
    if (!toolbarPos) return;
    const on = () => posicionarToolbar();
    window.addEventListener("scroll", on, true);
    const ro = new ResizeObserver(on);
    if (hojaRef.current) ro.observe(hojaRef.current);
    return () => {
      window.removeEventListener("scroll", on, true);
      ro.disconnect();
    };
  }, [toolbarPos, posicionarToolbar]);

  const toggleEnSeleccion = (key: string) => {
    actualizarSeleccion(
      new Set(
        seleccionRef.current.has(key)
          ? [...seleccionRef.current].filter((k) => k !== key)
          : [...seleccionRef.current, key],
      ),
    );
  };

  const onBloqueClick = (key: string, e: ReactMouseEvent) => {
    if (e.ctrlKey || e.metaKey || e.shiftKey) {
      toggleEnSeleccion(key);
      return;
    }
    if (seleccionRef.current.size > 1) {
      actualizarSeleccion(new Set([key]));
      onEditarBloque?.(key);
      return;
    }
    if (editando === key) {
      onCerrarEdicion?.();
      actualizarSeleccion(new Set());
    } else {
      actualizarSeleccion(new Set([key]));
      onEditarBloque?.(key);
    }
  };

  // Arrastre desde gutter o espacio vacío: seleccionar por rango.
  const gutterRef = useRef<HTMLDivElement | null>(null);

  const onGutterDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    setArrastre({ yInicio: e.clientY, yActual: e.clientY });
    onCerrarEdicion?.();
    actualizarSeleccion(new Set());
  };

  useEffect(() => {
    if (!arrastre) return;
    const yInicio = arrastre.yInicio;
    const onMove = (e: PointerEvent) => {
      setArrastre((a) => (a ? { ...a, yActual: e.clientY } : a));
      seleccionarRango(yInicio, e.clientY);
    };
    const onUp = () => setArrastre(null);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [arrastre, seleccionarRango]);

  // Reorden por handle.
  useEffect(() => {
    if (!reorden) return;
    const onMove = (e: PointerEvent) => {
      let over: string | null = null;
      let before = true;
      let bestDist = Infinity;
      bloqueRefs.current.forEach((el, k) => {
        if (k === reorden.dragKey) return;
        const r = el.getBoundingClientRect();
        const mid = r.top + r.height / 2;
        const dist = Math.abs(e.clientY - mid);
        if (dist < bestDist) {
          bestDist = dist;
          over = k;
          before = e.clientY < mid;
        }
      });
      setReorden((r) =>
        r ? { ...r, yActual: e.clientY, overKey: over, before } : r,
      );
    };
    const onUp = () => {
      const dragKey = reorden.dragKey;
      const overKey = reorden.overKey;
      const before = reorden.before;
      const moved = Math.abs(reorden.yActual - reorden.yInicio) > 6;
      setReorden(null);
      if (!moved) {
        toggleEnSeleccion(dragKey);
        return;
      }
      if (!overKey || dragKey === overKey) return;
      const keys = renders.map((b) => b.key);
      const from = keys.indexOf(dragKey);
      const to = keys.indexOf(overKey);
      if (from === -1 || to === -1) return;
      const sin = keys.filter((k) => k !== dragKey);
      const ins = before ? sin.indexOf(overKey) : sin.indexOf(overKey) + 1;
      sin.splice(ins, 0, dragKey);
      if (puedeEditar) onReordenar?.(sin);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [reorden, renders, onReordenar, puedeEditar]);

  const estilos = useCallback(() => {
    const keys = [...seleccion];
    const items = keys
      .map((k) => renders.find((r) => r.key === k))
      .filter((r): r is BloqueRender => Boolean(r));
    if (items.length === 0) return null;
    const alineaciones = new Set(items.map((i) => i.align));
    const bold = new Set(items.map((i) => i.bold));
    const underline = new Set(items.map((i) => i.underline));
    const size = new Set(
      items.map((i) => (i.size_pt ? `${Math.round(i.size_pt * 1.333)}px` : "")),
    );
    const font = new Set(items.map((i) => normalizarFuente(i.font) ?? ""));
    return {
      align: alineaciones.size === 1 ? [...alineaciones][0] : "",
      bold: bold.size === 1 ? [...bold][0] : undefined,
      underline: underline.size === 1 ? [...underline][0] : undefined,
      size_pt: size.size === 1 ? [...size][0] : "",
      font: font.size === 1 ? [...font][0] : "",
    };
  }, [seleccion, renders]);

  const estilosSel = estilos();

  const aplicarSeleccion = (cambio: PreviewOverride) => {
    if (!puedeEditar) return;
    const keys = [...seleccion];
    if (keys.length === 0) return;
    onAplicarSeleccion?.(keys, cambio);
  };

  return (
    <div className="doc-preview">
      <div className="doc-preview__toolbar">
        <span className="doc-preview__label">Tamaño de hoja</span>
        <select
          value={tamano}
          onChange={(e) => onTamanoChange?.(e.target.value as TamanoHoja)}
          aria-label="Tamaño de hoja"
        >
          <option value="carta">Carta</option>
          <option value="oficio">Oficio</option>
          <option value="a4">A4</option>
        </select>
        <span className="doc-preview__label">Márgenes</span>
        <select
          value={
            Object.entries(MARGENES_PRESETS).find(
              ([, v]) =>
                v.top === marg.top &&
                v.right === marg.right &&
                v.bottom === marg.bottom &&
                v.left === marg.left,
            )?.[0] ?? "Manual"
          }
          onChange={(e) => {
            if (!puedeEditar) return;
            if (e.target.value === "Manual") {
              onAbrirMargenesManual?.();
              return;
            }
            const p = MARGENES_PRESETS[e.target.value];
            if (p) onMargenesChange?.(p);
          }}
          disabled={!puedeEditar}
          aria-label="Preset de márgenes"
        >
          <option value="Estrecho">Estrecho</option>
          <option value="Normal">Normal</option>
          <option value="Legal">Legal 40mm</option>
          <option value="Amplio">Amplio</option>
          <option value="Manual">Manual…</option>
        </select>
        {puedeEditar && (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => onAbrirMargenesManual?.()}
            title="Ajustar márgenes manualmente"
          >
            mm
          </Button>
        )}
        {mostrarComparador && onToggleComparador && (
          <Button
            size="sm"
            variant={comparadorActivo ? "primary" : "secondary"}
            onClick={onToggleComparador}
            aria-pressed={comparadorActivo}
          >
            {comparadorActivo ? "Ocultar .docx" : "Ver .docx original"}
          </Button>
        )}
        {seleccion.size > 0 && (
          <span className="doc-preview__selcount">
            {seleccion.size} bloque{seleccion.size > 1 ? "s" : ""}
          </span>
        )}
        <span className="doc-preview__toolbar__spacer" />
        <Button
          size="sm"
          variant="secondary"
          iconOnly
          onClick={() => onDeshacer?.()}
          disabled={!canDeshacer}
          title="Deshacer (Ctrl+Z)"
          aria-label="Deshacer"
        >
          ↶
        </Button>
        <Button
          size="sm"
          variant="secondary"
          iconOnly
          onClick={() => onRehacer?.()}
          disabled={!canRehacer}
          title="Rehacer (Ctrl+Y)"
          aria-label="Rehacer"
        >
          ↷
        </Button>
        {puedeEditar && (
          <>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => onCancelarLocal?.()}
              disabled={!hayCambios || !!saving}
              title="Cancelar cambios locales"
            >
              Cancelar
            </Button>
            <Button
              size="sm"
              onClick={() => onGuardarTodo?.()}
              disabled={!hayCambios || !!saving}
              title="Guardar todo"
            >
              {saving ? "Guardando…" : "Guardar todo"}
            </Button>
          </>
        )}
      </div>

      <div
        ref={hojaRef}
        className="doc-preview__hoja"
        style={{
          width: `${dims.width}mm`,
          minHeight: `${dims.height}mm`,
          padding: `${marg.top}mm ${marg.right}mm ${marg.bottom}mm ${marg.left}mm`,
        }}
      >
        {/* Gutter de selección (overlay, no altera layout) */}
        <div
          ref={gutterRef}
          className="doc-preview__gutter"
          onPointerDown={onGutterDown}
          title="Arrastrar para seleccionar bloques"
        />
        {arrastre && (
          <div
            className="doc-preview__dragrect"
            style={{
              top: `${Math.min(arrastre.yInicio, arrastre.yActual) - (hojaRef.current?.getBoundingClientRect().top ?? 0)}px`,
              height: `${Math.abs(arrastre.yActual - arrastre.yInicio)}px`,
            }}
          />
        )}
        {reorden?.overKey &&
          (() => {
            const el = bloqueRefs.current.get(reorden.overKey!);
            const hoja = hojaRef.current;
            if (!el || !hoja) return null;
            const r = el.getBoundingClientRect();
            const h = hoja.getBoundingClientRect();
            const top = reorden.before ? r.top - h.top : r.bottom - h.top;
            return (
              <div
                className="doc-preview__dropline"
                style={{ top: `${top}px` }}
              />
            );
          })()}

        {renders.map((b) => {
          if (editando === b.key && editorSlot) {
            return (
              <div
                key={b.key}
                ref={(el) => {
                  if (el)
                    bloqueRefs.current.set(
                      b.key,
                      el as unknown as HTMLParagraphElement,
                    );
                  else bloqueRefs.current.delete(b.key);
                }}
                className="doc-preview__editing"
              >
                {editorSlot}
              </div>
            );
          }
          const sel = seleccion.has(b.key);
          const dragging = reorden?.dragKey === b.key;
          return (
            <div
              key={b.key}
              className={
                "doc-preview__row" +
                (dragging ? " doc-preview__row--dragging" : "")
              }
            >
              {puedeEditar && (
                <span
                  className="doc-preview__handle"
                  title="Arrastrar para mover · Click para seleccionar"
                  onPointerDown={(e) => {
                    if (e.button !== 0) return;
                    e.stopPropagation();
                    (e.currentTarget as HTMLElement).setPointerCapture(
                      e.pointerId,
                    );
                    setReorden({
                      dragKey: b.key,
                      yInicio: e.clientY,
                      yActual: e.clientY,
                      overKey: null,
                      before: true,
                    });
                    onCerrarEdicion?.();
                  }}
                >
                  ⋮⋮
                </span>
              )}
              <p
                ref={(el) => {
                  if (el) bloqueRefs.current.set(b.key, el);
                  else bloqueRefs.current.delete(b.key);
                }}
                className={
                  "doc-preview__bloque" +
                  (sel ? " doc-preview__bloque--sel" : "") +
                  " doc-preview__bloque--click"
                }
                style={{
                  textAlign: (b.align === "justify"
                    ? "justify"
                    : b.align) as CSSProperties["textAlign"],
                  fontWeight: b.bold ? 600 : 400,
                  textDecoration: b.underline ? "underline" : "none",
                  textTransform: b.allcaps ? "uppercase" : "none",
                  fontSize: b.size_pt ? `${b.size_pt * 1.333}px` : undefined,
                  fontFamily: fuenteCss(b.font),
                }}
                onClick={(e) => onBloqueClick(b.key, e)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onBloqueClick(b.key, e as unknown as ReactMouseEvent);
                  }
                }}
                role="button"
                tabIndex={0}
              >
                {segmentarPlaceholders(b.texto).map((seg, i) =>
                  seg.var ? (
                    <span key={i} className="doc-preview__placeholder">
                      {seg.valor}
                    </span>
                  ) : (
                    <span key={i}>
                      {segmentarNegrita(seg.valor).map((t, j) =>
                        t.negrita ? (
                          <strong key={j}>{t.texto}</strong>
                        ) : (
                          t.texto
                        ),
                      )}
                    </span>
                  ),
                )}
              </p>
            </div>
          );
        })}
        {puedeEditar && toolbarPos && estilosSel && (
          <SeleccionToolbar
            pos={toolbarPos}
            estilos={estilosSel}
            onAplicar={(c) => aplicarSeleccion(c)}
            cuenta={seleccion.size}
          />
        )}
      </div>
    </div>
  );
}

function SeleccionToolbar({
  pos,
  estilos,
  onAplicar,
  cuenta,
}: {
  pos: { top: number; left: number; abajo: boolean };
  estilos: {
    align: string;
    bold: boolean | undefined;
    underline: boolean | undefined;
    size_pt: string;
    font: string;
  };
  onAplicar: (c: PreviewOverride) => void;
  cuenta: number;
}) {
  return (
    <div
      className="doc-preview__flotante"
      style={{
        top: pos.abajo ? `${pos.top}px` : undefined,
        bottom: pos.abajo ? undefined : undefined,
        left: `${pos.left}px`,
        transform: pos.abajo ? "translateY(0)" : "translateY(-100%)",
      }}
    >
      <span className="doc-preview__flotante__label">
        Aplicando a {cuenta} bloque{cuenta > 1 ? "s" : ""}
      </span>
      <button
        type="button"
        className={estilos.bold ? "is-active" : ""}
        onClick={() => onAplicar({ bold: !estilos.bold })}
        title="Negrita"
      >
        N
      </button>
      <button
        type="button"
        className=""
        disabled
        style={{ opacity: 0.5, cursor: "not-allowed" }}
        title="Cursiva (texto, no persistido aquí)"
      >
        C
      </button>
      <button
        type="button"
        className={estilos.underline ? "is-active" : ""}
        onClick={() => onAplicar({ underline: !estilos.underline })}
        title="Subrayado"
      >
        S
      </button>
      <span className="formato-editor__sep" />
      {["left", "center", "right", "justify"].map((a) => (
        <button
          key={a}
          type="button"
          className={estilos.align === a ? "is-active" : ""}
          onClick={() => onAplicar({ align: a })}
        >
          {a === "left"
            ? "Izq"
            : a === "center"
              ? "Centro"
              : a === "right"
                ? "Der"
                : "Justif"}
        </button>
      ))}
      <span className="formato-editor__sep" />
      <select
        value={estilos.size_pt}
        onChange={(e) => {
          const px = e.target.value;
          const pt = px ? Math.round((parseFloat(px) / 1.333) * 10) / 10 : null;
          onAplicar({ size_pt: pt });
        }}
        aria-label="Tamaño de fuente"
      >
        {TAMANOS_PX.map((s) => (
          <option key={s} value={s}>
            {s ? `${s}` : "-"}
          </option>
        ))}
      </select>
      <select
        value={estilos.font}
        onChange={(e) => onAplicar({ font: e.target.value || null })}
        aria-label="Fuente"
      >
        {FUENTES.map((f) => (
          <option key={f} value={f}>
            {f || "-"}
          </option>
        ))}
      </select>
    </div>
  );
}
