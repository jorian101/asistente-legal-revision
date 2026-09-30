// Unit tests de la composición de etiquetas de fuentes (función pura, sin
// render). Cubre la lógica que ANTES solo se veía en el navegador: qué texto
// lee el usuario por cada cita, y sus casos borde (null, duplicados).

import { describe, expect, it } from "vitest";

import type { FragmentoCita } from "./chatTypes";
import { etiquetaFuente, resumenFuentes } from "./fuentesLabel";

function frag(partial: Partial<FragmentoCita>): FragmentoCita {
  return {
    id: 1,
    norma_id: null,
    obra_id: null,
    texto: "texto",
    referencia: null,
    nivel_jerarquico: null,
    ...partial,
  };
}

describe("etiquetaFuente", () => {
  it("OBRADO compone tipo · expediente · fecha", () => {
    const r = etiquetaFuente(
      frag({
        obra_id: 5,
        obra_tipo: "auto_vista",
        expediente_numero: "3349",
        obra_fecha_documento: "12/05/2025",
      }),
    );
    expect(r.badge).toBe("OBRADO");
    expect(r.esNorma).toBe(false);
    expect(r.etiqueta).toBe("Auto Vista · Exp. 3349 · 12/05/2025");
  });

  it("OBRADO sin expediente ni fecha muestra solo el tipo", () => {
    const r = etiquetaFuente(frag({ obra_id: 5, obra_tipo: "dictamen_fondo" }));
    expect(r.etiqueta).toBe("Dictamen Fondo");
  });

  it("NORMA con nombre formal distinto agrega nombre · referencia", () => {
    const r = etiquetaFuente(
      frag({
        norma_id: 4,
        referencia: "LOJM 3",
        norma_nombre: "Ley Organica de la Justicia Militar",
        norma_abreviatura: "LOJM",
      }),
    );
    expect(r.badge).toBe("NORMA");
    expect(r.esNorma).toBe(true);
    expect(r.etiqueta).toBe("Ley Organica de la Justicia Militar · LOJM 3");
  });

  it("NORMA con nombre == abreviatura NO duplica (regresión 'LOJM · LOJM 3')", () => {
    const r = etiquetaFuente(
      frag({
        norma_id: 4,
        referencia: "LOJM 3",
        norma_nombre: "LOJM",
        norma_abreviatura: "LOJM",
      }),
    );
    expect(r.etiqueta).toBe("LOJM 3");
    expect(r.etiqueta).not.toMatch(/LOJM · LOJM/);
  });

  it("NORMA sin enriquecimiento cae a la referencia (slug)", () => {
    const r = etiquetaFuente(frag({ norma_id: 4, referencia: "CPPM 184" }));
    expect(r.etiqueta).toBe("CPPM 184");
  });

  it("FRAGMENTO generico (sin norma ni obra) usa la referencia", () => {
    const r = etiquetaFuente(frag({ referencia: "Fragmento 2" }));
    expect(r.badge).toBe("FRAGMENTO");
    expect(r.etiqueta).toBe("Fragmento 2");
  });

  it("sin ningun dato devuelve etiqueta null (nunca 'null'/'undefined')", () => {
    const r = etiquetaFuente(frag({ norma_id: 1 }));
    expect(r.etiqueta).toBeNull();
  });
});

describe("etiquetaFuente — norma, jurisprudencia, doctrina y obrado", () => {
  it("una obra de tipo jurisprudencia se etiqueta JURISPRUDENCIA, no OBRADO", () => {
    const r = etiquetaFuente(
      frag({
        obra_id: 9,
        obra_tipo: "jurisprudencia",
        referencia: "SC 1180/2011-R",
      }),
    );
    expect(r.badge).toBe("JURISPRUDENCIA");
    expect(r.categoria).toBe("jurisprudencia");
    expect(r.etiqueta).toBe("SC 1180/2011-R");
  });

  it("el auto de vista oficializado (ejemplo) es jurisprudencia", () => {
    const r = etiquetaFuente(frag({ obra_id: 9, obra_tipo: "ejemplo" }));
    expect(r.categoria).toBe("jurisprudencia");
  });

  it("la categoria que envia el backend manda sobre la heuristica", () => {
    const sentencia = etiquetaFuente(
      frag({
        norma_id: 63,
        categoria: "jurisprudencia",
        referencia: "CIDH 71",
      }),
    );
    expect(sentencia.badge).toBe("JURISPRUDENCIA");
    expect(sentencia.etiqueta).toBe("CIDH 71");
    expect(
      etiquetaFuente(frag({ norma_id: 3, categoria: "doctrina" })).badge,
    ).toBe("DOCTRINA");
    expect(
      etiquetaFuente(frag({ norma_id: 1, categoria: "norma" })).badge,
    ).toBe("NORMA");
  });

  it("la doctrina tiene su propio badge y no arrastra el expediente", () => {
    const r = etiquetaFuente(
      frag({
        obra_id: 3,
        obra_tipo: "doctrina",
        expediente_numero: "3349",
        obra_fecha_documento: "2024-01-31",
      }),
    );
    expect(r.badge).toBe("DOCTRINA");
    expect(r.categoria).toBe("doctrina");
    expect(r.etiqueta).toBe("Doctrina · 2024-01-31");
  });

  it("criterio y doctrina_libro también son doctrina", () => {
    expect(
      etiquetaFuente(frag({ obra_id: 1, obra_tipo: "doctrina_libro" })).badge,
    ).toBe("DOCTRINA");
    expect(
      etiquetaFuente(frag({ obra_id: 1, obra_tipo: "criterio" })).badge,
    ).toBe("DOCTRINA");
  });

  it("una sentencia del expediente sigue siendo un obrado del caso", () => {
    const r = etiquetaFuente(frag({ obra_id: 2, obra_tipo: "sentencia" }));
    expect(r.badge).toBe("OBRADO");
    expect(r.categoria).toBe("obrado");
  });
});

describe("resumenFuentes", () => {
  it("cuenta normas, jurisprudencia, obrados y doctrina por separado", () => {
    const r = resumenFuentes([
      frag({ norma_id: 1 }),
      frag({ obra_id: 9, obra_tipo: "jurisprudencia" }),
      frag({ norma_id: 8, categoria: "jurisprudencia" }),
      frag({ obra_id: 3, obra_tipo: "doctrina" }),
      frag({ obra_id: 4, obra_tipo: "auto_vista" }),
    ]);
    expect(r).toBe("1 norma · 2 jurisprudencia · 1 obrado · 1 doctrina");
  });
});
