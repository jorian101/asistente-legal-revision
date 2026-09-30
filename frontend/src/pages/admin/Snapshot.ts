// Snapshot: estado local de cambios de un formato para Undo/Redo.
import type { PreviewOverride } from "./DocumentoPreview";

export interface Snapshot {
  overrides: Record<string, PreviewOverride>;
  ordenLocal: string[] | null;
  aEliminar: string[];
}
