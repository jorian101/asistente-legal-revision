// Historial de deshacer/rehacer por pasos para las ediciones pendientes de un obrado.
// Antes "Deshacer" era descartar todo (setOverrides({})) y "Rehacer" nunca se habilitaba.
//
// `grupo`: cambios consecutivos con el mismo grupo (lo que se tipea seguido en un mismo
// bloque) cuentan como un solo paso, para que Deshacer no vaya de a una letra.
import { useCallback, useRef, useState } from "react";

interface Estado<T> {
  pasado: T[];
  presente: T;
  futuro: T[];
}

export function useHistorial<T>(inicial: T) {
  const [h, setH] = useState<Estado<T>>({
    pasado: [],
    presente: inicial,
    futuro: [],
  });
  const ultimoGrupo = useRef<string | null>(null);

  const cambiar = useCallback(
    (f: (prev: T) => T, grupo: string | null = null) => {
      // Fuera del updater: React (StrictMode) lo ejecuta dos veces y debe ser puro.
      const mismoPaso = grupo !== null && grupo === ultimoGrupo.current;
      ultimoGrupo.current = grupo;
      setH((s) => ({
        pasado: mismoPaso ? s.pasado : [...s.pasado, s.presente],
        presente: f(s.presente),
        futuro: [],
      }));
    },
    [],
  );

  const deshacer = useCallback(() => {
    ultimoGrupo.current = null;
    setH((s) =>
      s.pasado.length === 0
        ? s
        : {
            pasado: s.pasado.slice(0, -1),
            presente: s.pasado[s.pasado.length - 1],
            futuro: [s.presente, ...s.futuro],
          },
    );
  }, []);

  const rehacer = useCallback(() => {
    ultimoGrupo.current = null;
    setH((s) =>
      s.futuro.length === 0
        ? s
        : {
            pasado: [...s.pasado, s.presente],
            presente: s.futuro[0],
            futuro: s.futuro.slice(1),
          },
    );
  }, []);

  const reiniciar = useCallback((valor: T) => {
    ultimoGrupo.current = null;
    setH({ pasado: [], presente: valor, futuro: [] });
  }, []);

  return {
    estado: h.presente,
    cambiar,
    deshacer,
    rehacer,
    reiniciar,
    puedeDeshacer: h.pasado.length > 0,
    puedeRehacer: h.futuro.length > 0,
  };
}
