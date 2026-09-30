// ¿El bloque ENTERO tiene la marca (negrita, subrayado)? El editor usaba `isActive`, que mira
// solo el texto bajo el cursor: la negrita guardada dependía de dónde quedaba el cursor, y al
// cerrar el editor se reemitía ese estado (un título perdía la negrita sin que nadie la tocara).

interface NodoTexto {
  isText: boolean;
  text?: string | null;
  marks: readonly { type: { name: string } }[];
}

interface Documento {
  descendants(f: (nodo: NodoTexto) => boolean | void): void;
}

export function todoConMarca(doc: Documento, marca: string): boolean {
  let hayTexto = false;
  let todo = true;
  doc.descendants((nodo) => {
    if (nodo.isText && nodo.text?.trim()) {
      hayTexto = true;
      if (!nodo.marks.some((m) => m.type.name === marca)) todo = false;
    }
  });
  return hayTexto && todo;
}
