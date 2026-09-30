// Fuentes: página única de gestión de normas, jurisprudencia y doctrina (libros) en
// /asistente/doctrina. Flujo común privada -> pendiente -> global: el operador sube y
// propone; el supervisor aprueba (o rechaza con motivo) y ve las colas de
// recomendaciones y de promociones de obrados.

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { CATEGORIA_LABEL, type CategoriaFuente } from "../../api/fuentes";
import {
  listarExpedientes,
  type ExpedienteResumen,
} from "../../api/expedientes";
import { PanelCategoria } from "../../components/fuentes/PanelCategoria";
import { PromocionesPendientes } from "../../components/fuentes/PromocionesPendientes";
import { RecomendacionesPendientes } from "../../components/fuentes/RecomendacionesPendientes";
import { PageHeader, Tabs } from "../../components/ui";
import { useAuth } from "../../context/useAuth";

type Pestana = CategoriaFuente | "recomendaciones" | "promociones";

const CATEGORIAS: CategoriaFuente[] = ["norma", "jurisprudencia", "doctrina"];

export default function Fuentes() {
  const { auth } = useAuth();
  const esSupervisor = auth?.rol === "supervisor";
  // ?categoria= llega desde la búsqueda global al elegir una fuente.
  const [params] = useSearchParams();
  const inicial = params.get("categoria") as CategoriaFuente | null;
  const [pestana, setPestana] = useState<Pestana>(
    inicial && CATEGORIAS.includes(inicial) ? inicial : "norma",
  );
  const [expedientes, setExpedientes] = useState<ExpedienteResumen[]>([]);
  const [expedientesTotal, setExpedientesTotal] = useState(0);

  useEffect(() => {
    listarExpedientes({ por_pagina: 100 })
      .then((r) => {
        setExpedientes(r.items);
        setExpedientesTotal(r.total);
      })
      .catch(() => setExpedientes([]));
  }, []);

  const pestanas: [Pestana, string][] = [
    ...CATEGORIAS.map((c): [Pestana, string] => [c, CATEGORIA_LABEL[c]]),
    ...(esSupervisor
      ? ([
          ["recomendaciones", "Fuentes sugeridas"],
          ["promociones", "Obrados propuestos"],
        ] as [Pestana, string][])
      : []),
  ];

  return (
    <div>
      <PageHeader
        title="Fuentes"
        subtitle="Normas, jurisprudencia y doctrina: sube, propone y fija las fuentes de tus consultas."
      />
      <Tabs
        ariaLabel="Tipo de fuente"
        items={pestanas.map(([value, label]) => ({ value, label }))}
        value={pestana}
        onChange={setPestana}
      />
      {pestana === "recomendaciones" ? (
        <RecomendacionesPendientes />
      ) : pestana === "promociones" ? (
        <PromocionesPendientes />
      ) : (
        <PanelCategoria
          key={pestana}
          categoria={pestana}
          esSupervisor={esSupervisor}
          expedientes={expedientes}
          expedientesTotal={expedientesTotal}
        />
      )}
    </div>
  );
}
