// FragmentoPreview: preview de un fragmento jurídico de la timeline, en un
// Modal md (título = norma/obrado, contexto jerárquico como subtítulo).

import { Button, Modal } from "../ui";

import "./FragmentoPreview.css";

interface FragmentoPreviewProps {
  fragmento: {
    id: number;
    texto: string;
    norma_id?: number;
    obra_id?: number;
    norma_abreviatura?: string;
    obra_titulo?: string;
    nivel_jerarquico?: number;
    score?: number;
    breadcrumb?: string[];
  } | null;
  onClose: () => void;
}

export function FragmentoPreview({
  fragmento,
  onClose,
}: FragmentoPreviewProps): React.JSX.Element | null {
  if (!fragmento) return null;

  const titulo = fragmento.norma_abreviatura
    ? `${fragmento.norma_abreviatura} (norma #${fragmento.norma_id})`
    : fragmento.obra_titulo
      ? `${fragmento.obra_titulo} (obrado #${fragmento.obra_id})`
      : `Fragmento #${fragmento.id}`;

  const breadcrumb = fragmento.breadcrumb?.length
    ? fragmento.breadcrumb.join(" › ")
    : null;

  return (
    <Modal
      open
      title={titulo}
      subtitle={breadcrumb ? `Contexto: ${breadcrumb}` : undefined}
      onClose={onClose}
      footer={
        <Button variant="secondary" onClick={onClose}>
          Cerrar
        </Button>
      }
    >
      {(fragmento.nivel_jerarquico != null || fragmento.score != null) && (
        <div className="fragmento-preview__meta">
          {fragmento.nivel_jerarquico != null && (
            <span>
              <strong>Nivel:</strong> {fragmento.nivel_jerarquico}
            </span>
          )}
          {fragmento.score != null && (
            <span>
              <strong>Score:</strong> {fragmento.score.toFixed(3)}
            </span>
          )}
        </div>
      )}
      <div className="fragmento-preview__texto">{fragmento.texto}</div>
    </Modal>
  );
}
