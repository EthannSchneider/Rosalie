import { api } from "./client.js";

/** { enabled, repo, base, code_model, problems, supervised, version, busy, reasons, notice, operations } */
export const getEvolution = () => api.get("/evolution");
export const requestChange = (brief) => api.post("/evolution", brief);
export const mergePull = (id) => api.post(`/evolution/${id}/merge`);
export const updateAndRestart = (id) => api.post(`/evolution/${id}/update`);
