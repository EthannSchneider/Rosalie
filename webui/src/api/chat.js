import { API_BASE, api, enc } from "./client.js";

export const PAGE = 50;
export const EVENTS_URL = `${API_BASE}/chat/events`;

export const getMessages = (before) =>
  api.get(`/chat/messages${before ? `?before=${before}` : ""}`).then((data) => data.messages);
export const sendMessage = (text) => api.post("/chat/messages", { text }).then((data) => data.message);
export const clearMessages = () => api.delete("/chat/messages");
export const sendTyping = () => api.post("/chat/typing");
export const answerConfirmation = (id, accept) => api.post(`/chat/confirmations/${id}`, { accept });
export const fileUrl = (id) => `${API_BASE}/chat/files/${enc(id)}`;
