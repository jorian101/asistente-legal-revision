// Test estatico: index.css respeta prefers-reduced-motion (WCAG 2.3.3, PRODUCT.md).
//
// jsdom no evalua media queries de CSS, asi que se comprueba que el bloque
// global exista y anule animaciones, transiciones y scroll suave.

/// <reference types="node" />
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const css = readFileSync(join(process.cwd(), "src/index.css"), "utf-8");

describe("index.css: prefers-reduced-motion", () => {
  it("declara el bloque global", () => {
    expect(css).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)/);
  });

  it("anula animaciones, transiciones y scroll suave", () => {
    const bloque = css.slice(css.indexOf("prefers-reduced-motion"));
    expect(bloque).toMatch(/animation-duration:\s*0\.01ms\s*!important/);
    expect(bloque).toMatch(/transition-duration:\s*0\.01ms\s*!important/);
    expect(bloque).toMatch(/scroll-behavior:\s*auto\s*!important/);
  });
});
