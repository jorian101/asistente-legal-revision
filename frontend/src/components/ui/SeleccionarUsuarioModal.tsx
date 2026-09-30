// SeleccionarUsuarioModal: picker de usuarios (buscador + filtro por rol).
// Compartido por Sala de control y Permisos por usuario.

import { ROL_LABEL, labelRol } from "../../config/modulosPorRol";
import { Badge } from "./Badge";
import { SelectorModal } from "./SelectorModal";

interface UsuarioElegible {
  id: number;
  carnet: string;
  nombre: string;
  rol: string;
  cargo: string;
  activo: boolean;
}

interface Props<U extends UsuarioElegible> {
  open: boolean;
  usuarios: U[] | null;
  seleccionado?: number;
  onSeleccionar: (u: U) => void;
  onClose: () => void;
}

export function SeleccionarUsuarioModal<U extends UsuarioElegible>({
  open,
  usuarios,
  seleccionado,
  onSeleccionar,
  onClose,
}: Props<U>) {
  return (
    <SelectorModal
      open={open}
      title="Seleccionar usuario"
      opciones={
        usuarios?.map((u) => ({
          id: String(u.id),
          titulo: `${u.carnet} · ${u.nombre}`,
          detalle: [labelRol(u.rol), u.cargo].filter(Boolean).join(" · "),
          segmento: u.rol,
          extra: !u.activo && <Badge tone="neutral">Inactivo</Badge>,
        })) ?? null
      }
      segmentos={Object.entries(ROL_LABEL)}
      placeholder="Buscar por carnet, nombre o cargo"
      seleccionado={
        seleccionado === undefined ? undefined : String(seleccionado)
      }
      onSeleccionar={(id) => {
        const u = usuarios?.find((x) => String(x.id) === id);
        if (u) onSeleccionar(u);
      }}
      onClose={onClose}
    />
  );
}
