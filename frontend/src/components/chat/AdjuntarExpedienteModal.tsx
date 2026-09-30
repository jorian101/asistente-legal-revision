// AdjuntarExpedienteModal: selector de expedientes del usuario para adjuntar
// al chat (Fase 3A). Carga los expedientes via listarExpedientes y los muestra
// en el SelectorModal compartido (buscador por número, procesado o delito;
// filtro activos/archivados; aviso si la lista viene truncada).

import { useEffect, useState } from "react";

import {
  listarExpedientes,
  type PaginaExpedientes,
  type ExpedienteResumen,
} from "../../api/expedientes";
import { mensajeError } from "../../lib/errors";
import { toast } from "../../lib/toasts";
import { SelectorModal } from "../ui";

interface Props {
  abierto: boolean;
  onCerrar: () => void;
  onSeleccionar: (expediente: ExpedienteResumen) => void;
}

export function AdjuntarExpedienteModal({
  abierto,
  onCerrar,
  onSeleccionar,
}: Props) {
  const [pagina, setPagina] = useState<PaginaExpedientes | null>(null);

  useEffect(() => {
    if (!abierto) return;
    setPagina(null);
    listarExpedientes({ por_pagina: 100 })
      .then(setPagina)
      .catch((err) => {
        setPagina({ items: [], total: 0, pagina: 1, por_pagina: 100 });
        toast(
          mensajeError(err, "No se pudieron cargar los expedientes."),
          "error",
        );
      });
  }, [abierto]);

  const expedientes = pagina?.items ?? [];

  return (
    <SelectorModal
      open={abierto}
      title="Adjuntar expediente"
      subtitle="El chat operará sobre su contexto: autos de vista, dictámenes y obrados."
      opciones={
        pagina === null
          ? null
          : expedientes.map((e) => ({
              id: String(e.id),
              titulo: `Nº ${e.numero_caso}`,
              detalle: [e.procesado_nombre, e.delito]
                .filter(Boolean)
                .join(" · "),
              segmento: e.estado,
            }))
      }
      segmentos={[
        ["activo", "Activos"],
        ["archivado", "Archivados"],
      ]}
      placeholder="Buscar por número, procesado o delito"
      aviso={
        pagina !== null &&
        pagina.total > expedientes.length &&
        `Se muestran los ${expedientes.length} más recientes de ${pagina.total}.`
      }
      vacio="No tenés expedientes. Abrí uno en la sección Expedientes primero."
      onSeleccionar={(id) => {
        const e = expedientes.find((x) => String(x.id) === id);
        if (e) onSeleccionar(e);
      }}
      onClose={onCerrar}
    />
  );
}
