import { api, enc } from "./client.js";

/** { roles: [...], permissions: [{ name, label, description }] } */
export const listRoles = () => api.get("/roles");
export const createRole = (role) => api.post("/roles", role);
export const updateRole = (name, changes) => api.patch(`/roles/${enc(name)}`, changes);
export const deleteRole = (name) => api.delete(`/roles/${enc(name)}`);
