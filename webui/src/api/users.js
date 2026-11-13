import { api } from "./client.js";

export const listUsers = () => api.get("/users").then((data) => data.users);
export const createUser = (user) => api.post("/users", user).then((data) => data.users);
export const updateUser = (id, changes) => api.patch(`/users/${id}`, changes).then((data) => data.users);
export const deleteUser = (id) => api.delete(`/users/${id}`).then((data) => data.users);
