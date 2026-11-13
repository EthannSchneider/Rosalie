import { api } from "./client.js";

export const changePassword = (current, password) => api.put("/account/password", { current, password });
export const linkDiscord = (discordId) => api.put("/account/discord", { discord_id: discordId });
