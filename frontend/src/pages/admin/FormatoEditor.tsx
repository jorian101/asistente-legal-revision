// FormatoEditor: edición WYSIWYG tipo Word del contenido de un formato.
//
// Usa TipTap (ProseMirror) para que el supervisor edite como en Word:
// negrita, cursiva, subrayado, alineación (izq/centro/derecha), y tamaño.
// Los placeholders {{VAR}} se insertan como texto y se resaltan visualmente
// para que el usuario sepa que son variables (no se editan a mano).

import { useEditor, EditorContent } from "@tiptap/react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "../../components/ui";
import { fuenteCss, normalizarFuente } from "../../lib/fuentes";
import { EXTENSIONES_BLOQUE } from "../../lib/extensionesBloque";
import { todoConMarca } from "../../lib/marcasBloque";
import { textoDeDoc } from "../../lib/textoBloque";

// Sus estilos viven en Formatos.css: sin importarlo acá, fuera de la página de Formatos
// (p. ej. Obrados generados) la hoja y la barra salían sin estilo.
import "./Formatos.css";

export interface CambioBloque {
  texto: string;
  align: string;
  bold: boolean;
  underline: boolean;
  size_pt: number | null;
  font: string | null;
}

export interface EstiloInicial {
  align?: string;
  bold?: boolean;
  underline?: boolean;
  size_pt?: number | null;
  font?: string | null;
}

interface FormatoEditorProps {
  inicial: string;
  onGuardar: (c: CambioBloque) => void;
  onCancelar: () => void;
  onCambio?: (c: CambioBloque) => void;
  disabled?: boolean;
  modo?: "panel" | "inline";
  estiloInicial?: EstiloInicial;
  /** Sin formatos.actualizar: vista de solo lectura (sin barra ni Guardar). */
  puedeEditar?: boolean;
}

const PLACEHOLDER_RE = /\{\{[^}]+\}\}/g;

function leerCambio(editor: ReturnType<typeof useEditor>): CambioBloque | null {
  if (!editor) return null;
  const texto = textoDelEditor(editor);
  const align =
    (["center", "right", "justify"].find((a) =>
      editor.isActive({ textAlign: a }),
    ) as string) ?? "left";
  // Leer size_pt y font desde el primer nodo de texto si hay estilo aplicado.
  const dom = editor.view.dom as HTMLElement;
  const firstMarked = dom.querySelector(
    "[style*='font-size'], [style*='font-family']",
  );
  let size_pt: number | null = null;
  let font: string | null = null;
  if (firstMarked) {
    const fs = (firstMarked as HTMLElement).style.fontSize;
    if (fs) {
      const px = parseFloat(fs);
      if (!Number.isNaN(px)) size_pt = Math.round((px / 1.333) * 10) / 10;
    }
    const ff = (firstMarked as HTMLElement).style.fontFamily;
    if (ff)
      font = normalizarFuente(ff.split(",")[0].trim().replace(/['"]/g, ""));
  }
  return {
    texto,
    align,
    // Del bloque entero, no del texto bajo el cursor (isActive): ver lib/marcasBloque.
    bold: todoConMarca(editor.state.doc, "bold"),
    underline: todoConMarca(editor.state.doc, "underline"),
    size_pt,
    font,
  };
}

export default function FormatoEditor({
  inicial,
  onGuardar,
  onCancelar,
  onCambio,
  disabled = false,
  modo = "panel",
  estiloInicial,
  puedeEditar = true,
}: FormatoEditorProps) {
  const [tamanoActivo, setTamanoActivo] = useState<string>(
    estiloInicial?.size_pt
      ? `${Math.round(estiloInicial.size_pt * 1.333)}px`
      : "",
  );
  const [fuenteActiva, setFuenteActiva] = useState<string>(
    normalizarFuente(estiloInicial?.font) ?? "",
  );

  const editorRef = useRef<ReturnType<typeof useEditor>>(null);
  // Cambios que hace el propio editor (sembrar fuente/tamaño al abrir, recargar el contenido
  // tras Deshacer) no son ediciones del usuario: sin esto, abrir un bloque ya lo marcaba como
  // cambiado y recargar tras Deshacer borraba lo que se podía Rehacer.
  const sembrando = useRef(false);

  const sincronizarEstilo = useCallback(() => {
    if (!editorRef.current) return;
    const c = leerCambio(editorRef.current);
    if (!c) return;
    setTamanoActivo(c.size_pt ? `${Math.round(c.size_pt * 1.333)}px` : "");
    setFuenteActiva(c.font ?? "");
  }, []);

  const editor = useEditor({
    editable: puedeEditar,
    extensions: EXTENSIONES_BLOQUE,
    content: htmlDeTexto(inicial, estiloInicial),
    editorProps: {
      attributes: {
        class: "formato-editor__area",
      },
    },
    onCreate({ editor: ed }) {
      editorRef.current = ed as unknown as ReturnType<typeof useEditor>;
      // Sembrar fuente/tamaño del bloque al montar para que el editor abra
      // con el estilo correcto desde el primer frame (no espera onUpdate).
      const e = ed as unknown as ReturnType<typeof useEditor>;
      const docSize = e.state.doc.content.size - 1;
      sembrando.current = true;
      const fuenteInicial = normalizarFuente(estiloInicial?.font);
      if (fuenteInicial) {
        e.chain().selectAll().setFontFamily(fuenteInicial).run();
      }
      if (estiloInicial?.size_pt) {
        e.chain()
          .selectAll()
          .setFontSize(`${Math.round(estiloInicial.size_pt * 1.333)}px`)
          .run();
      }
      e.chain().focus().setTextSelection(docSize).run();
      sembrando.current = false;
    },
    onUpdate({ editor: ed }) {
      editorRef.current = ed as unknown as ReturnType<typeof useEditor>;
      sincronizarEstilo();
      // Solo lectura, o cambios del propio editor: no son ediciones del usuario.
      if (!onCambio || !puedeEditar || sembrando.current) return;
      const c = leerCambio(ed as unknown as ReturnType<typeof useEditor>);
      if (c) onCambio(c);
    },
  });

  // Si el texto o el estilo del bloque cambian desde afuera (barra flotante, Deshacer) con el
  // editor abierto, recargarlo: si no, mostraba otra cosa y al cerrarse pisaba ese cambio.
  useEffect(() => {
    if (!editor) return;
    const c = leerCambio(editor);
    if (c && !igualAlInicial(c, inicial, estiloInicial)) {
      sembrando.current = true;
      editor.commands.setContent(htmlDeTexto(inicial, estiloInicial));
      sembrando.current = false;
    }
  }, [inicial, estiloInicial, editor]);

  // Props más recientes para emitir al perder el foco o al cerrarse, sin volver a suscribir
  // en cada render: antes el efecto dependía de onCambio/estiloInicial (se recrean en cada
  // render) y su limpieza emitía el estado del editor en CADA render, pisando otros cambios.
  const actual = useRef({ onCambio, inicial, estiloInicial });
  actual.current = { onCambio, inicial, estiloInicial };

  useEffect(() => {
    if (!editor || !puedeEditar) return;
    // Solo si difiere de lo que muestra el bloque: abrir y cerrar no es un cambio pendiente.
    const emitirSiCambio = () => {
      const {
        onCambio: emitir,
        inicial: txt,
        estiloInicial: est,
      } = actual.current;
      const c = leerCambio(editor);
      if (emitir && c && !igualAlInicial(c, txt, est)) emitir(c);
    };
    editor.on("blur", emitirSiCambio);
    return () => {
      editor.off("blur", emitirSiCambio);
      emitirSiCambio(); // al cerrarse: no perder lo escrito sin Guardar
    };
  }, [editor, puedeEditar]);

  const guardar = useCallback(() => {
    if (!editor) return;
    const c = leerCambio(editor);
    if (c) onGuardar(c);
  }, [editor, onGuardar]);

  const setAlineacion = (align: "left" | "center" | "right" | "justify") => {
    editor?.chain().focus().setTextAlign(align).run();
    // TipTap aplica align async; notificar al siguiente tick para que isActive refleje el valor real
    if (onCambio) {
      setTimeout(() => {
        const c = leerCambio(editor);
        if (c) onCambio({ ...c, align });
        sincronizarEstilo();
      }, 0);
    }
  };

  const toggleMark = (mark: "bold" | "underline") => {
    if (mark === "bold") editor?.chain().focus().toggleBold().run();
    else editor?.chain().focus().toggleUnderline().run();
    if (onCambio) {
      setTimeout(() => {
        const c = leerCambio(editor);
        if (c) onCambio(c);
        sincronizarEstilo();
      }, 0);
    }
  };

  const setTamanio = (px: string) => {
    if (!editor) return;
    // Aplicar al bloque completo: seleccionar todo el contenido y cambiar el tamaño.
    const chain = editor.chain().focus().selectAll();
    if (px) chain.setFontSize(px).run();
    else chain.unsetFontSize().run();
    // Colapsar al final para no dejar todo seleccionado.
    editor
      .chain()
      .focus()
      .setTextSelection(editor.state.doc.content.size - 1)
      .run();
    setTamanoActivo(px);
    if (onCambio) {
      setTimeout(() => {
        const c = leerCambio(editor);
        if (c) onCambio(c);
      }, 0);
    }
  };

  const setFuente = (f: string) => {
    if (!editor) return;
    // Aplicar al bloque completo para que se vea el cambio en todo el bloque.
    editor.chain().focus().selectAll().setFontFamily(f).run();
    editor
      .chain()
      .focus()
      .setTextSelection(editor.state.doc.content.size - 1)
      .run();
    setFuenteActiva(f);
    if (onCambio) {
      setTimeout(() => {
        const c = leerCambio(editor);
        if (c) onCambio(c);
      }, 0);
    }
  };

  if (!editor) return null;

  if (modo === "inline") {
    return (
      <div
        className="formato-editor formato-editor--inline"
        style={
          estiloInicial?.font || estiloInicial?.size_pt
            ? {
                fontFamily: fuenteCss(estiloInicial.font),
                fontSize: estiloInicial.size_pt
                  ? `${Math.round(estiloInicial.size_pt * 1.333)}px`
                  : undefined,
              }
            : undefined
        }
      >
        <div className="formato-editor__toolbar formato-editor__toolbar--flotante">
          {puedeEditar && (
            <>
              <button
                type="button"
                className={editor.isActive("bold") ? "is-active" : ""}
                onClick={() => toggleMark("bold")}
                disabled={!editor.can().toggleBold()}
              >
                N
              </button>
              <button
                type="button"
                className={editor.isActive("italic") ? "is-active" : ""}
                onClick={() => editor.chain().focus().toggleItalic().run()}
              >
                C
              </button>
              <button
                type="button"
                className={editor.isActive("underline") ? "is-active" : ""}
                onClick={() => toggleMark("underline")}
              >
                S
              </button>
              <span className="formato-editor__sep" />
              <button
                type="button"
                className={
                  editor.isActive({ textAlign: "left" }) ? "is-active" : ""
                }
                onClick={() => setAlineacion("left")}
              >
                Izq
              </button>
              <button
                type="button"
                className={
                  editor.isActive({ textAlign: "center" }) ? "is-active" : ""
                }
                onClick={() => setAlineacion("center")}
              >
                Centro
              </button>
              <button
                type="button"
                className={
                  editor.isActive({ textAlign: "right" }) ? "is-active" : ""
                }
                onClick={() => setAlineacion("right")}
              >
                Der
              </button>
              <button
                type="button"
                className={
                  editor.isActive({ textAlign: "justify" }) ? "is-active" : ""
                }
                onClick={() => setAlineacion("justify")}
              >
                Justificar
              </button>
              <span className="formato-editor__sep" />
              <select
                className="formato-editor__size"
                aria-label="Tamaño de letra"
                value={tamanoActivo}
                onChange={(e) => setTamanio(e.target.value)}
              >
                <option value="">Tamaño</option>
                <option value="12px">12</option>
                <option value="13px">13</option>
                <option value="14px">14</option>
                <option value="16px">16</option>
                <option value="18px">18</option>
                <option value="20px">20</option>
                <option value="24px">24</option>
              </select>
              <select
                className="formato-editor__font"
                aria-label="Fuente"
                value={fuenteActiva}
                onChange={(e) => setFuente(e.target.value)}
              >
                <option value="">Fuente</option>
                <option value="Arial">Arial</option>
                <option value="Times New Roman">Times New Roman</option>
                <option value="Courier New">Courier New</option>
                <option value="Georgia">Georgia</option>
              </select>
              <span className="formato-editor__sep" />
              <button
                type="button"
                className="formato-editor__inline-ok"
                onClick={guardar}
                disabled={disabled}
                title="Guardar"
              >
                {disabled ? "…" : "✓"}
              </button>
            </>
          )}
          <button
            type="button"
            className="formato-editor__inline-cancel"
            onClick={onCancelar}
            disabled={disabled}
            title={puedeEditar ? "Cancelar" : "Cerrar"}
            aria-label={puedeEditar ? "Cancelar" : "Cerrar"}
          >
            ✕
          </button>
        </div>
        <EditorContent editor={editor} />
      </div>
    );
  }

  return (
    <div className="formato-editor">
      {puedeEditar && (
        <div className="formato-editor__toolbar">
          <button
            type="button"
            onClick={() => toggleMark("bold")}
            disabled={!editor.can().toggleBold()}
          >
            N
          </button>
          <button
            type="button"
            onClick={() => editor.chain().focus().toggleItalic().run()}
          >
            C
          </button>
          <button type="button" onClick={() => toggleMark("underline")}>
            S
          </button>
          <span className="formato-editor__sep" />
          <button type="button" onClick={() => setAlineacion("left")}>
            Izq
          </button>
          <button type="button" onClick={() => setAlineacion("center")}>
            Centro
          </button>
          <button type="button" onClick={() => setAlineacion("right")}>
            Der
          </button>
          <button type="button" onClick={() => setAlineacion("justify")}>
            Justificar
          </button>
        </div>
      )}

      <EditorContent editor={editor} />

      <div className="formato-editor__footer">
        <Button variant="secondary" onClick={onCancelar} disabled={disabled}>
          {puedeEditar ? "Cancelar" : "Cerrar"}
        </Button>
        {puedeEditar && (
          <Button onClick={guardar} disabled={disabled}>
            {disabled ? "Guardando…" : "Guardar"}
          </Button>
        )}
      </div>
    </div>
  );
}

// Texto del bloque tal como lo guarda el modelo: **negrita en línea** y "\n" entre líneas.
function textoDelEditor(
  editor: NonNullable<ReturnType<typeof useEditor>>,
): string {
  const doc = editor.state.doc;
  return textoDeDoc(doc, todoConMarca(doc, "bold"));
}

function aPx(size_pt: number | null | undefined): number | null {
  return size_pt ? Math.round(size_pt * 1.333) : null;
}

function igualAlInicial(
  c: CambioBloque,
  inicial: string,
  estilo?: EstiloInicial,
): boolean {
  return (
    c.texto === inicial &&
    c.bold === !!estilo?.bold &&
    c.underline === !!estilo?.underline &&
    c.align === (estilo?.align ?? "left") &&
    // En píxeles, como lo guarda el editor: en puntos el redondeo nunca coincidía.
    aPx(c.size_pt) === aPx(estilo?.size_pt) &&
    (c.font ?? null) === normalizarFuente(estilo?.font)
  );
}

// Convierte el texto del bloque (placeholders {{VAR}}, **negrita** y "\n") a HTML editable,
// sembrando el estilo del bloque (align/bold/underline/size/font) como marcas activas.
function htmlDeTexto(texto: string, estilo?: EstiloInicial): string {
  return texto
    .split("\n")
    .map((linea) => htmlDeLinea(linea, estilo))
    .join("");
}

function htmlDeLinea(texto: string, estilo?: EstiloInicial): string {
  const partes = texto.split(PLACEHOLDER_RE);
  const matches = texto.match(PLACEHOLDER_RE) ?? [];
  let inner = "";
  for (let i = 0; i < partes.length; i++) {
    inner += escaparHtml(partes[i]).replace(
      /\*\*([^*]+)\*\*/g,
      "<strong>$1</strong>",
    );
    if (i < matches.length) {
      inner += `<span class="formato-editor__placeholder">${matches[i]}</span>`;
    }
  }
  let contenido = inner;
  if (estilo?.bold) contenido = `<strong>${contenido}</strong>`;
  if (estilo?.underline) contenido = `<u>${contenido}</u>`;
  const styles: string[] = [];
  if (estilo?.size_pt)
    styles.push(`font-size:${Math.round(estilo.size_pt * 1.333)}px`);
  const fuente = normalizarFuente(estilo?.font);
  if (fuente) styles.push(`font-family:"${fuente}"`);
  const styleAttr = styles.length ? ` style="${styles.join(";")}"` : "";
  const align =
    estilo?.align && estilo.align !== "left"
      ? ` style="text-align:${estilo.align}"`
      : "";
  return `<p${align}><span${styleAttr}>${contenido}</span></p>`;
}

function escaparHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
