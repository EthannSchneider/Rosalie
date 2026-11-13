import { api, enc } from "./client.js";

export const getSettings = () => api.get("/settings");
export const saveSettings = (changes) => api.patch("/settings", { changes });
export const getModels = () => api.get("/settings/models").then((data) => data.models);
export const getPersona = (name) => api.get(`/personas/${enc(name)}`);
export const savePersona = (name, text, create) => api.put(`/personas/${enc(name)}`, { text, create });
export const renamePersona = (name, to) => api.post(`/personas/${enc(name)}/rename`, { to });
export const deletePersona = (name) => api.delete(`/personas/${enc(name)}`);
export const activatePersona = (name) => api.post(`/personas/${enc(name)}/activate`);
