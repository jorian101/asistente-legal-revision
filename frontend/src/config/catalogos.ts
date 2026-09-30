// Catálogos del sistema derivados del vault de investigación.
//
// Fuente: wiki/variables/diccionario-variables-expediente.md (vault
// asistente-legal-vault) + wiki/auditoria/fuentes-catalogos-potenciales.md.
//
// Regla del vault (anti-alucinación): cada catálogo conserva el valor
// normalizado como guardado en BD; si el dato real no está catalogado, el
// formulario ofrece "Otro" con texto libre (nunca se fuerza un valor).
//
// Forma: catálogo = `readonly CatOption[]`, donde `valor` es lo que se guarda
// y `label` lo que se muestra. Los helpers `obtenerLabel` buscan el label de
// un valor (fallback: mostrar el valor tal cual).

export interface CatOption {
  valor: string;
  label: string;
}

// --- Tipos de proceso (backed: backend TipoProceso) ---

export const TIPO_PROCESO: readonly CatOption[] = [
  { valor: "consulta", label: "Consulta" },
  { valor: "apelacion_incidental", label: "Apelación incidental" },
  { valor: "apelacion_restringida", label: "Apelación restringida" },
];

// --- Delitos (diccionario-variables-expediente: tipo_delito) ---

export const TIPO_DELITO: readonly CatOption[] = [
  { valor: "desercion", label: "Deserción" },
  { valor: "abandono_servicio", label: "Abandono (del servicio)" },
  { valor: "abandono_y_maltrato", label: "Abandono del servicio y maltrato" },
  { valor: "abandono_puesto", label: "Abandono de puesto militar" },
  { valor: "hurto", label: "Hurto" },
  { valor: "robo", label: "Robo" },
  { valor: "homicidio", label: "Homicidio" },
  { valor: "falsificacion", label: "Falsificación" },
  { valor: "falta_incorporacion", label: "Falta de incorporación" },
  { valor: "maltrato", label: "Maltrato" },
  { valor: "malversacion", label: "Malversación" },
  {
    valor: "incumplimiento_cambio_destino",
    label: "Incumplimiento de cambio de destino",
  },
  { valor: "suplantacion", label: "Suplantación" },
  { valor: "estafa", label: "Estafa" },
  { valor: "lesiones", label: "Lesiones" },
  { valor: "fraude", label: "Fraude" },
  { valor: "violacion_normas", label: "Violación de normas" },
  { valor: "sustraccion", label: "Sustracción" },
  { valor: "uso_documentos_falsos", label: "Uso de documentos falsos" },
  { valor: "injurias_superiores", label: "Injurias a superiores" },
  { valor: "robo_armas", label: "Robo de armas" },
];

// --- Grados militares (diccionario-variables-expediente: grado_militar) ---

export const GRADO_MILITAR: readonly CatOption[] = [
  { valor: "general", label: "General (GRAL.)" },
  { valor: "coronel", label: "Coronel (CNL.)" },
  { valor: "teniente_coronel", label: "Teniente Coronel (TCNL.)" },
  { valor: "mayor", label: "Mayor (MY.)" },
  { valor: "capitan", label: "Capitán (CAP.)" },
  { valor: "teniente", label: "Teniente (TTE.)" },
  { valor: "subteniente", label: "Subteniente (SBTTE.)" },
  { valor: "sargento", label: "Sargento (SGTO)" },
  { valor: "soldado", label: "Soldado (SLDO)" },
  { valor: "sargento_primero", label: "Sargento Primero (SOF.)" },
  { valor: "sargento_segundo", label: "Sargento Segundo (SR.)" },
  { valor: "cabo", label: "Cabo" },
  { valor: "civil", label: "Civil" },
];

// --- Tribunales de origen (casos TSJM: TPJM, cámaras, auditoría) ---

export const TRIBUNAL_ORIGEN: readonly CatOption[] = [
  { valor: "tpjm", label: "Tribunal Permanente de Justicia Militar (TPJM)" },
  { valor: "camara_a", label: "Cámara A" },
  { valor: "camara_b", label: "Cámara B" },
  { valor: "auditoria", label: "Auditoría" },
];

// --- Fuerza (diccionario-variables-expediente: fuerza) ---

export const FUERZA: readonly CatOption[] = [
  { valor: "ejercito", label: "Ejército" },
  { valor: "fuerza_aerea", label: "Fuerza Aérea" },
  { valor: "armada", label: "Armada" },
  { valor: "civil", label: "Civil" },
  { valor: "mindefensa", label: "Ministerio de Defensa" },
];

// --- Resultado del auto de vista (diccionario: resultado_auto_vista) ---

export const RESULTADO_AUTO_VISTA: readonly CatOption[] = [
  { valor: "confirmar", label: "Confirma" },
  { valor: "aprobar", label: "Aprueba" },
  { valor: "revocar", label: "Revoca" },
  { valor: "modificar", label: "Modifica" },
  { valor: "improcedente", label: "Improcedente" },
  { valor: "anular", label: "Anula" },
  { valor: "procedente", label: "Procedente" },
];

// --- Sentido de la sentencia (diccionario: sentido_sentencia) ---

export const SENTIDO_SENTENCIA: readonly CatOption[] = [
  { valor: "condenatoria", label: "Condenatoria" },
  { valor: "absolutoria", label: "Absolutoria" },
  { valor: "inocente", label: "Inocente" },
  { valor: "culpable", label: "Culpable" },
  { valor: "sobreseido", label: "Sobreseído" },
];

// --- Helpers ---

/** Devuelve el label de un valor de catálogo; si no está, devuelve el valor. */
export function obtenerLabel(
  catalogo: readonly CatOption[],
  valor: string,
): string {
  return catalogo.find((c) => c.valor === valor)?.label ?? valor;
}
