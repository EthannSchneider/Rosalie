import { api } from "./client.js";

export const getSession = () => api.get("/session");
export const setup = (code, username, password) => api.post("/session/setup", { code, username, password });
export const login = (username, password) => api.post("/session/login", { username, password });
export const logout = () => api.post("/session/logout");
