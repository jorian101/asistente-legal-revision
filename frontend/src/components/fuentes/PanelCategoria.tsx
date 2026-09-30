// Panel de una categoría de fuentes (norma, jurisprudencia o doctrina) con el flujo
// común: global · mis fuentes · pendientes (supervisor). Acciones: subir, proponer,
// aprobar/rechazar con motivo, fijar al caso y recomendar a un expediente.
// Cada fila muestra solo las acciones que su estado admite (máx. tres).

import { useCallback, useEffect, useState } from "react";
import { Plus, Search, X } from "lucide-react";

import {
  CATEGORIA_LABEL,
  ESTADO_LABEL,
  SUBGRUPO_LABEL,
  listarFuentes,
  listarResolucionesTribunal,
  proponerFuente,
  recomendarFuente,
  resolverFuente,
  seleccionarFuente,
  type CategoriaFuente,
  type FuenteDTO,
  type ResolucionTribunalDTO,
} from "../../api/fuentes";
import type { ExpedienteResumen } from "../../api/expedientes";
import { usePermisos } from "../../context/usePermisos";
import { mensajeError } from "../../lib/errors";
import { toast } from "../../lib/toasts";

import {
  Badge,
  Button,
  SelectorModal,
  StateMessage,
  type BadgeTone,
} from "../ui";
import { RechazoModal } from "./RechazoModal";
import { SubirFuenteForm } from "./SubirFuenteForm";
import styles from "./Fuentes.module.css";

type Filtro = "todas" | "globales" | "mias" | "pendientes";

const TONO_ESTADO: Record<FuenteDTO["estado_visibilidad"], BadgeTone> = {
  global: "success",
  pendiente: "warning",
  privado: "neutral",
  rechazado: "danger",
};

const SINGULAR: Record<CategoriaFuente, string> = {
  norma: "norma",
  jurisprudencia: "sentencia",
  doctrina: "libro",
};

const normalizar = (s: string) =>
  s
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();

interface Props {
  categoria: CategoriaFuente;
  esSupervisor: boolean;
  expedientes: ExpedienteResumen[];
  /** Total en el servidor: si supera a `expedientes`, la lista vino truncada. */
  expedientesTotal: number;
}

export function PanelCategoria({
  categoria,
  esSupervisor,
  expedientes,
  expedientesTotal,
}: Props) {
  const [fuentes, setFuentes] = useState<FuenteDTO[] | null>(null);
  const [resoluciones, setResoluciones] = useState<ResolucionTribunalDTO[]>([]);
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [expedienteId, setExpedienteId] = useState("");
  const [selectorExpediente, setSelectorExpediente] = useState(false);
  // Fuentes = módulo "doctrina": crear (subir, fijar), actualizar (proponer,
  // recomendar). Sin permiso, el botón no se muestra.
  const { puede } = usePermisos();
  const puedeCrear = puede("doctrina", "crear");
  const puedeActualizar = puede("doctrina", "actualizar");
  // Fuente con una acción en curso: sus botones quedan deshabilitados.
  const [ocupadoId, setOcupadoId] = useState<number | null>(null);
  const [subirAbierto, setSubirAbierto] = useState(false);
  const [rechazoDe, setRechazoDe] = useState<FuenteDTO | null>(null);
  const [query, setQuery] = useState("");

  const cargar = useCallback(() => {
    setFuentes(null);
    listarFuentes(categoria)
      .then(setFuentes)
      .catch((err) => {
        setFuentes([]);
        toast(mensajeError(err, "No se pudieron cargar las fuentes."), "error");
      });
    if (categoria === "jurisprudencia") {
      listarResolucionesTribunal()
        .then(setResoluciones)
        .catch(() => setResoluciones([]));
    }
  }, [categoria]);

  useEffect(cargar, [cargar]);

  async function accion(
    id: number,
    fn: () => Promise<unknown>,
    ok: string,
    fallo: string,
  ) {
    setOcupadoId(id);
    try {
      await fn();
      toast(ok, "success");
      cargar();
    } catch (err) {
      toast(mensajeError(err, fallo), "error");
    } finally {
      setOcupadoId(null);
    }
  }

  function confirmarRechazo(motivo: string) {
    if (rechazoDe === null) return;
    const id = rechazoDe.id;
    setRechazoDe(null);
    void accion(
      id,
      () => resolverFuente(id, false, motivo),
      "Fuente rechazada.",
      "No se pudo rechazar.",
    );
  }

  const q = normalizar(query.trim());
  const visibles = (fuentes ?? []).filter((f) =>
    q && !normalizar(`${f.nombre} ${f.abreviatura}`).includes(q)
      ? false
      : filtro === "globales"
        ? f.estado_visibilidad === "global"
        : filtro === "mias"
          ? f.es_propia
          : filtro === "pendientes"
            ? f.estado_visibilidad === "pendiente"
            : true,
  );

  const grupos: { titulo: string | null; items: FuenteDTO[] }[] =
    categoria === "jurisprudencia"
      ? (["tcp", "cidh"] as const).map((g) => ({
          titulo: SUBGRUPO_LABEL[g],
          items: visibles.filter((f) => f.subgrupo === g),
        }))
      : [{ titulo: null, items: visibles }];

  const exp = expedienteId ? Number(expedienteId) : null;

  function fila(f: FuenteDTO) {
    return (
      <li key={f.id} className={styles.item}>
        <div className={styles.info}>
          <strong className={styles.nombre} title={f.nombre}>
            {f.nombre}
          </strong>
          <span className={styles.meta}>
            {f.abreviatura}
            {f.es_propia ? " · Mía" : ""}
            <Badge tone={TONO_ESTADO[f.estado_visibilidad]}>
              {ESTADO_LABEL[f.estado_visibilidad]}
            </Badge>
          </span>
          {f.motivo_rechazo && (
            <span className={styles.motivo}>Rechazada: {f.motivo_rechazo}</span>
          )}
        </div>
        <div className={styles.acciones}>
          {esSupervisor && f.estado_visibilidad === "pendiente" && (
            <>
              <Button
                size="sm"
                disabled={ocupadoId === f.id}
                onClick={() =>
                  void accion(
                    f.id,
                    () => resolverFuente(f.id, true),
                    "Fuente aprobada.",
                    "No se pudo aprobar.",
                  )
                }
              >
                Aprobar
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={ocupadoId === f.id}
                onClick={() => setRechazoDe(f)}
              >
                Rechazar
              </Button>
            </>
          )}
          {puedeActualizar &&
            f.es_propia &&
            f.estado_visibilidad === "privado" && (
              <Button
                size="sm"
                variant="secondary"
                disabled={ocupadoId === f.id}
                onClick={() =>
                  void accion(
                    f.id,
                    () => proponerFuente(f.id),
                    "Propuesta enviada al supervisor.",
                    "No se pudo proponer.",
                  )
                }
              >
                Proponer
              </Button>
            )}
          {puedeActualizar && f.estado_visibilidad === "global" && (
            <Button
              size="sm"
              variant="ghost"
              disabled={exp === null || ocupadoId === f.id}
              title={exp === null ? "Elegí un expediente arriba" : undefined}
              onClick={() =>
                exp !== null &&
                void accion(
                  f.id,
                  () => recomendarFuente(categoria, f.abreviatura, exp),
                  esSupervisor
                    ? "Fuente recomendada."
                    : "Recomendación enviada al supervisor.",
                  "No se pudo recomendar.",
                )
              }
            >
              Recomendar
            </Button>
          )}
          {puedeCrear && (
            <Button
              size="sm"
              variant="secondary"
              disabled={ocupadoId === f.id}
              onClick={() =>
                void accion(
                  f.id,
                  () => seleccionarFuente(f.id, exp),
                  "Fuente fijada.",
                  "No se pudo fijar la fuente.",
                )
              }
            >
              Fijar
            </Button>
          )}
        </div>
      </li>
    );
  }

  return (
    <section aria-label={CATEGORIA_LABEL[categoria]}>
      <div className={styles.barra}>
        <label className={styles.buscar}>
          <Search size={16} aria-hidden="true" />
          <input
            type="search"
            className="input"
            placeholder={`Buscar en ${CATEGORIA_LABEL[categoria].toLowerCase()}…`}
            aria-label={`Buscar en ${CATEGORIA_LABEL[categoria]}`}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <div className={styles.filtros} role="group" aria-label="Filtrar">
          {(
            [
              ["todas", "Todas"],
              ["globales", "Globales"],
              ["mias", "Mis fuentes"],
              ...(esSupervisor ? [["pendientes", "Pendientes"]] : []),
            ] as [Filtro, string][]
          ).map(([valor, texto]) => (
            <button
              key={valor}
              type="button"
              className={styles.filtro}
              aria-pressed={filtro === valor}
              onClick={() => setFiltro(valor)}
            >
              {texto}
            </button>
          ))}
        </div>
        <div className={styles.expediente}>
          <span id={`expediente-${categoria}`}>Expediente</span>
          <Button
            variant="secondary"
            size="sm"
            aria-haspopup="dialog"
            aria-describedby={`expediente-${categoria}`}
            onClick={() => setSelectorExpediente(true)}
          >
            {expedientes.find((e) => String(e.id) === expedienteId)
              ?.numero_caso ?? "Sin expediente (consulta)"}
          </Button>
        </div>
        <SelectorModal
          open={selectorExpediente}
          title="Elegir expediente"
          opciones={[
            { id: "", titulo: "Sin expediente (consulta)" },
            ...expedientes.map((e) => ({
              id: String(e.id),
              titulo: `Nº ${e.numero_caso}`,
              detalle: [e.procesado_nombre, e.delito]
                .filter(Boolean)
                .join(" · "),
              segmento: e.estado,
            })),
          ]}
          segmentos={[
            ["activo", "Activos"],
            ["archivado", "Archivados"],
          ]}
          placeholder="Buscar por número, procesado o delito"
          aviso={
            expedientesTotal > expedientes.length &&
            `Se muestran los ${expedientes.length} más recientes de ${expedientesTotal}.`
          }
          seleccionado={expedienteId}
          onSeleccionar={(id) => {
            setExpedienteId(id);
            setSelectorExpediente(false);
          }}
          onClose={() => setSelectorExpediente(false)}
        />
        {puedeCrear && (
          <Button
            variant={subirAbierto ? "secondary" : "primary"}
            onClick={() => setSubirAbierto((v) => !v)}
            aria-expanded={subirAbierto}
          >
            {subirAbierto ? (
              <>
                <X aria-hidden="true" size={16} />
                Cancelar
              </>
            ) : (
              <>
                <Plus aria-hidden="true" size={16} />
                Subir {SINGULAR[categoria]}
              </>
            )}
          </Button>
        )}
      </div>

      {puedeCrear && subirAbierto && (
        <SubirFuenteForm
          categoria={categoria}
          esSupervisor={esSupervisor}
          onSubida={() => {
            setSubirAbierto(false);
            cargar();
          }}
        />
      )}

      {fuentes === null ? (
        <StateMessage tipo="cargando" />
      ) : q && visibles.length === 0 ? (
        <StateMessage tipo="vacio">
          Ninguna fuente coincide con «{query.trim()}».
        </StateMessage>
      ) : (
        grupos.map((g) => (
          <div key={g.titulo ?? "todas"}>
            {g.titulo && (
              <h3 className={styles.grupo}>
                {g.titulo}
                <span className={styles.cuenta}>{g.items.length}</span>
              </h3>
            )}
            {g.items.length === 0 ? (
              <p className={styles.vacio}>Sin fuentes.</p>
            ) : (
              <ul className={styles.lista}>{g.items.map(fila)}</ul>
            )}
          </div>
        ))
      )}

      {categoria === "jurisprudencia" && (
        <div>
          <h3 className={styles.grupo}>Resoluciones del tribunal</h3>
          {resoluciones.length === 0 ? (
            <p className={styles.vacio}>
              Aún no hay obrados promovidos ni autos de vista oficializados.
            </p>
          ) : (
            <ul className={styles.lista}>
              {resoluciones.map((r) => (
                <li key={r.obra_id} className={styles.item}>
                  <div className={styles.info}>
                    <strong>{r.nombre_archivo}</strong>
                    <span className={styles.meta}>
                      {r.tipo_documento === "ejemplo"
                        ? "Auto oficializado"
                        : "Obrado promovido"}
                      {r.expediente_id
                        ? ` · Expediente ${r.expediente_id}`
                        : ""}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <RechazoModal
        nombre={rechazoDe?.nombre ?? null}
        onCancelar={() => setRechazoDe(null)}
        onConfirmar={confirmarRechazo}
      />
    </section>
  );
}
