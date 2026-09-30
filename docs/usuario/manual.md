# Manual de usuario — Asistente Legal

Asistente para el tribunal militar: responde consultas sobre el corpus jurídico (normas,
jurisprudencia y doctrina) y genera borradores de dictámenes y autos de vista a partir de los
obrados de un expediente, citando siempre sus fuentes.

**Todo funciona en tu máquina.** Ni las consultas ni los obrados salen de ella: no se usa ningún
servicio de internet. La aplicación se niega a arrancar si alguien la configura para enviar datos
afuera.

---

## 1. Requisitos

|             | Mínimo                                                                                                           | Recomendado |
| ----------- | ---------------------------------------------------------------------------------------------------------------- | ----------- |
| Sistema     | Windows 10/11, macOS 12+ o Linux                                                                                 | —           |
| Memoria RAM | 8 GB                                                                                                             | 16 GB       |
| Disco libre | 20 GB                                                                                                            | 40 GB       |
| Programa    | [Docker Desktop](https://www.docker.com/products/docker-desktop/) (en Linux: Docker Engine con `docker compose`) | —           |

La RAM la usa sobre todo el modelo que redacta las respuestas (`llama3:8b` por defecto). Con menos de
8 GB elegí un modelo más liviano (sección 5).

La aplicación viene completa en el paquete. Internet hace falta **solo la primera vez**, para
descargar los modelos de lenguaje (varios GB). Después se trabaja sin conexión, y las
actualizaciones tampoco la necesitan.

## 2. Instalar

1. Instalá Docker Desktop y abrilo (tiene que quedar corriendo).
2. Copiá la carpeta del paquete (`asistente-legal-vX.Y.Z`, la entrega el equipo de desarrollo en
   un USB o carpeta compartida) a una ubicación fija, por ejemplo `Documentos\AsistenteLegal`.
3. Ejecutá el instalador desde esa carpeta:
   - **Windows**: clic derecho en la carpeta → _Abrir en Terminal_, y:
     ```powershell
     powershell -ExecutionPolicy Bypass -File .\instalar.ps1
     ```
   - **macOS / Linux**: en una terminal, dentro de la carpeta:
     ```bash
     ./instalar.sh
     ```

La primera vez tarda (descarga varios GB). Al final muestra:

```
Administrador creado. Usuario: admin  Contraseña: ••••••••••••
Listo: abrí http://localhost:8080 en el navegador.
```

**Anotá la contraseña: no se vuelve a mostrar.** Entrá con ella y cambiala desde tu perfil.

Si algo falla, el instalador dice en qué paso se detuvo. Corregí la causa (ver sección 8) y volvé
a ejecutarlo: retoma sin duplicar nada.

> No borres el archivo `.env` de la carpeta: guarda las claves de tus bases de datos. Sin él, la
> instalación no puede leer sus propios datos.

## 3. Primer uso

1. Abrí `http://localhost:8080` y entrá como `admin`.
2. En **Administración → Usuarios** creá las cuentas de cada persona con su rol:
   - **Operador jurídico** (fiscal, auditor, vocal): consulta, carga obrados y genera borradores.
   - **Supervisor** (vocal presidente): además revisa y aprueba lo que proponen los operadores.
   - **Administrador**: gestiona usuarios y la configuración.
3. Cada persona entra con su usuario y cambia su contraseña desde el perfil.

El corpus jurídico (normas, jurisprudencia y doctrina públicas) ya viene cargado.

## 4. Trabajo diario

- **Consultas**: escribí la pregunta en el asistente. La respuesta cita las normas, sentencias o
  libros en los que se apoya; revisá siempre esas citas antes de usar el texto.
- **Expedientes y obrados**: abrí un expediente y cargá sus obrados (PDF o Word; los PDF escaneados
  se leen con OCR). Cada obrado se carga por separado, con su tipo. Los obrados son privados de
  quien los carga, salvo que se publiquen.
- **Borradores**: desde un expediente, pedí el borrador del documento (dictamen, auto de vista…).
  El borrador es un punto de partida: se revisa y corrige antes de firmarlo.
- **Fuentes propias**: normas, jurisprudencia o libros nuevos se cargan como privados. Para que
  todos los vean, el operador los propone y un supervisor los aprueba.

## 5. Cambiar el modelo que redacta

El modelo se define en el archivo `.env` de la carpeta de instalación (`LLM_MODEL_NAME`).

| Modelo                    | RAM aprox. | Comentario                           |
| ------------------------- | ---------- | ------------------------------------ |
| `llama3.2:3b`             | 4 GB       | Para equipos modestos; redacta peor. |
| `llama3:8b` (por defecto) | 8 GB       | Equilibrio calidad/recursos.         |
| `qwen2.5:14b`             | 16 GB      | Mejor redacción, más lento sin GPU.  |

Para cambiarlo:

```bash
docker compose -f compose.usuario.yml exec ollama ollama pull llama3.2:3b
# editar .env: LLM_MODEL_NAME=llama3.2:3b
docker compose -f compose.usuario.yml up -d app
```

**No cambies `EMBEDDING_MODEL_NAME`**: el corpus está indexado con ese modelo y dejaría de
encontrarse.

## 6. Actualizar a una versión nueva

1. Copiá los archivos del paquete de la versión nueva **sobre** la carpeta de instalación
   (sin borrar `.env`).
2. Ejecutá el actualizador con el número de versión:
   - Windows: `powershell -ExecutionPolicy Bypass -File .\actualizar.ps1 0.4.0`
   - macOS / Linux: `./actualizar.sh 0.4.0`

Antes de tocar nada guarda un respaldo completo en `respaldos/`. Si la versión nueva no arranca,
**vuelve sola a la anterior** y restaura ese respaldo. Si falla antes de cambiar de versión (por
ejemplo, falta `imagen-X.Y.Z.tar` en la carpeta y no hay internet), vuelve a levantar la versión
que ya tenías. Tus datos no se pierden en ningún caso.

## 7. Respaldos

Cada actualización deja un respaldo en `respaldos/<fecha>-v<versión>/`:
`postgres.dump` (usuarios, expedientes, historial), `qdrant_data.tgz` (índice de búsqueda) y
`uploads.tgz` (archivos subidos).

- **Respaldo manual**: `./actualizar.sh` solo respalda al cambiar de versión. Para un respaldo en
  cualquier momento, copiá la carpeta de instalación completa con la app detenida
  (`docker compose -f compose.usuario.yml stop`) o pedí ayuda a tu área de TI.
- Guardá copias fuera de la máquina (disco externo): los obrados son información sensible, tratala
  como tal.

## 8. Problemas frecuentes

| Síntoma                                                | Qué hacer                                                                                                                                                           |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Falta Docker` / `Cannot connect to the Docker daemon` | Abrí Docker Desktop y esperá a que diga _running_.                                                                                                                  |
| El instalador se corta en _5/7 modelos_                | Falta conexión o espacio en disco. Liberá espacio y volvé a correrlo.                                                                                               |
| `http://localhost:8080` no abre                        | `docker compose -f compose.usuario.yml ps`: los servicios tienen que figurar _running_. Si `app` se reinicia, ver `docker compose -f compose.usuario.yml logs app`. |
| Las respuestas tardan mucho                            | Sin GPU el modelo corre en el procesador. Elegí un modelo más liviano (sección 5).                                                                                  |
| `MODO_LOCAL=1 pero ... endpoint externo`               | Alguien configuró un servicio de internet en `.env`. Borrá esas líneas (`LLM_ENDPOINTS`, `EMBEDDING_ENDPOINTS`, `RERANKER_ENDPOINTS`).                              |
| Otro programa usa el puerto 8080                       | Cambiá `PUERTO_APP` en `.env` y ejecutá `docker compose -f compose.usuario.yml up -d app`.                                                                          |

## 9. Desinstalar

```bash
docker compose -f compose.usuario.yml down        # detiene todo, conserva los datos
docker compose -f compose.usuario.yml down -v     # BORRA también todos los datos
```

Después se puede borrar la carpeta de instalación.
