// Extensiones del editor de un bloque de obrado. Un bloque guarda texto con **negrita en
// línea** y saltos "\n" (lib/textoBloque), más estilo de bloque (alineación, negrita,
// subrayado, tamaño, fuente). Lo que no se puede guardar se apaga: antes el editor aceptaba
// listas ("1. ", "- "), citas ("> "), títulos, código, cursiva y tachado, y al cerrar el
// bloque se perdían sin aviso (una lista dejaba la línea vacía).
import TextAlign from "@tiptap/extension-text-align";
import { FontFamily, FontSize, TextStyle } from "@tiptap/extension-text-style";
import Underline from "@tiptap/extension-underline";
import StarterKit from "@tiptap/starter-kit";

export const EXTENSIONES_BLOQUE = [
  StarterKit.configure({
    blockquote: false,
    bulletList: false,
    orderedList: false,
    listItem: false,
    listKeymap: false,
    codeBlock: false,
    heading: false,
    horizontalRule: false,
    italic: false,
    strike: false,
    code: false,
    link: false,
    underline: false, // se agrega abajo: StarterKit 3 ya la trae y quedaba duplicada
  }),
  Underline,
  TextAlign.configure({ types: ["paragraph"] }),
  TextStyle,
  FontSize,
  FontFamily,
];
