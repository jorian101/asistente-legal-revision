"""Módulo de use cases de permisos CRUD por módulo.

Decision `plan/permisos-crud-modulos`. Conjunto de UCs para el sistema de
módulos y permisos CRUD por usuario:
- listar_modulos — catálogo fijo de módulos.
- actualizar_modulo — metadata (nombre/descripcion/ruta/orden/activo).
- listar_permisos_usuario — override + efectivo por módulo de un usuario.
- asignar_permisos_usuario — reemplazar overrides de un usuario (no admin).
- resolver_permisos_usuario — permisos efectivos (defaults rol ⊕ overrides);
  usado por el guard require_permiso en cada request.
- mis_permisos — módulos activos + efectivos del usuario logueado (sidebar).
- modulos_visibles — módulos efectivos de cada usuario y de cada rol (gestión de usuarios).
"""
