// Texto de un bloque de obrado: negrita en línea como **…** (misma convención Markdown del
// contenido) y saltos de línea como "\n". La negrita del bloque ENTERO es un atributo del
// bloque (bold), no se escribe con asteriscos.
//
// Antes el editor guardaba `textContent`: la negrita de una palabra se perdía, un Enter pegaba
// las palabras de los dos párrafos, y la vista previa mostraba los ** literales.

export function segmentarNegrita(
  texto: string,
): Array<{ texto: string; negrita: boolean }> {
  return texto
    .split(/(\*\*[^*]+\*\*)/g)
    .filter((t) => t.length > 0)
    .map((t) =>
      t.startsWith("**") && t.endsWith("**") && t.length > 4
        ? { texto: t.slice(2, -2), negrita: true }
        : { texto: t, negrita: false },
    );
}

interface Marca {
  type: { name: string };
}
interface NodoPM {
  type?: { name: string };
  isText: boolean;
  text?: string | null;
  marks: readonly Marca[];
  forEach(f: (hijo: NodoPM) => void): void;
}

/** Documento del editor -> texto del bloque. `negritaDeBloque`: no se escriben ** (va en bold). */
export function textoDeDoc(doc: NodoPM, negritaDeBloque: boolean): string {
  const lineas: string[] = [];
  doc.forEach((parrafo) => {
    let linea = "";
    let enNegrita = false;
    parrafo.forEach((hijo) => {
      if (hijo.type?.name === "hardBreak") {
        linea += "\n"; // Shift+Enter: salto de línea (antes pegaba las palabras)
        return;
      }
      if (!hijo.isText || !hijo.text) return;
      const negrita =
        !negritaDeBloque && hijo.marks.some((m) => m.type.name === "bold");
      if (negrita !== enNegrita) {
        linea += "**";
        enNegrita = negrita;
      }
      linea += hijo.text;
    });
    if (enNegrita) linea += "**";
    lineas.push(linea.replace(/ /g, " "));
  });
  return lineas.join("\n");
}
