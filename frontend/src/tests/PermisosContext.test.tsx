// PermisosProvider no debe vaciar los permisos en cada refresh del access
// token: eso desmontaba las rutas `requireModulo` cada hora.

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AuthState } from "../api/auth";
import { PermisosProvider } from "../context/PermisosContext";
import { AuthContext, type AuthContextValue } from "../context/useAuth";
import { usePermisos } from "../context/usePermisos";

const { obtenerPermisosPropios } = vi.hoisted(() => ({
  obtenerPermisosPropios: vi.fn(),
}));
vi.mock("../api/permisos", () => ({ obtenerPermisosPropios }));

function Estado() {
  const { permisos } = usePermisos();
  return <p>{permisos === null ? "cargando" : `${permisos.length} módulos`}</p>;
}

function conAuth(auth: AuthState) {
  const value = {
    auth,
    isAuthenticated: auth.access_token !== null,
  } as AuthContextValue;
  return (
    <AuthContext.Provider value={value}>
      <PermisosProvider>
        <Estado />
      </PermisosProvider>
    </AuthContext.Provider>
  );
}

const usuario: AuthState = {
  access_token: "t1",
  rol: "operador_juridico",
  carnet: "1",
  nombre: "Op",
  id: 7,
};

describe("PermisosProvider", () => {
  beforeEach(() => {
    obtenerPermisosPropios.mockReset();
    obtenerPermisosPropios.mockResolvedValue([{ clave: "consultas" }]);
  });

  it("un refresh del token no vacía ni recarga los permisos", async () => {
    const { rerender } = render(conAuth(usuario));
    await screen.findByText("1 módulos");

    rerender(conAuth({ ...usuario, access_token: "t2" }));

    expect(screen.getByText("1 módulos")).toBeInTheDocument();
    expect(obtenerPermisosPropios).toHaveBeenCalledTimes(1);
  });

  it("recarga cuando cambia el usuario", async () => {
    const { rerender } = render(conAuth(usuario));
    await screen.findByText("1 módulos");

    rerender(conAuth({ ...usuario, id: 8, access_token: "t3" }));

    await waitFor(() =>
      expect(obtenerPermisosPropios).toHaveBeenCalledTimes(2),
    );
  });
});
