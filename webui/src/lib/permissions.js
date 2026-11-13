// Ce que le compte connecté peut faire : permissions de son rôle (libs/models/role.py).
//   can(user, "settings")              une permission
//   can(user, ["settings", "personas"]) au moins une
export function can(user, permission) {
  const wanted = Array.isArray(permission) ? permission : [permission];
  return Boolean(user) && wanted.some((p) => user.permissions.includes(p));
}

/** Peut-on attribuer ce rôle ? (mêmes règles que le serveur : controllers/guards.py) */
export function canAssign(user, role) {
  if (role.name === "superadmin" && !user.superadmin) return false;
  return role.permissions.every((p) => user.permissions.includes(p));
}
