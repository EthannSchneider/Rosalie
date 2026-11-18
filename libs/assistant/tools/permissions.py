"""Quelle permission (libs/models/role.py) faut-il pour que Rosalie utilise chaque outil ?

Chaque outil DOIT être ici (un test le vérifie) : un outil oublié serait refusé à tous sauf au
terminal. Les personnes sans compte (inconnus sur Discord) n'ont que « web », si le réglage
guest_web le permet.
"""
TOOL_PERMISSIONS: dict[str, str] = {
    # Recherche web (pas une « act.* » : n'en fait pas une owner)
    "web_search": "web",
    "fetch_url": "web",
    "weather": "web",
    # Relances et messages
    "say": "act.followups",
    "plan_followup": "act.followups",
    "cancel_followup": "act.followups",
    # Souvenirs
    "remember": "act.memory",
    "recall": "act.memory",
    "forget": "act.memory",
    # Photos
    "send_image": "act.images",
    "send_image_url": "act.images",
    # Discord : lire
    "list_servers": "act.discord_read",
    "list_channels": "act.discord_read",
    "list_members": "act.discord_read",
    "server_info": "act.discord_read",
    "member_info": "act.discord_read",
    "list_roles": "act.discord_read",
    "read_messages": "act.discord_read",
    "search_messages": "act.discord_read",
    # Discord : écrire
    "send_message": "act.discord_write",
    "send_dm": "act.discord_write",
    "react": "act.discord_write",
    "pin_message": "act.discord_write",
    "edit_message": "act.discord_write",
    "create_poll": "act.discord_write",
    "create_thread": "act.discord_write",
    # Discord : gérer le serveur
    "create_channel": "act.discord_manage",
    "delete_channel": "act.discord_manage",
    "set_status": "act.discord_manage",
    "create_invite": "act.discord_manage",
    "purge_messages": "act.discord_manage",
    "delete_message": "act.discord_manage",
    # Discord : modérer
    "add_role": "act.discord_moderate",
    "remove_role": "act.discord_moderate",
    "kick_member": "act.discord_moderate",
    "ban_member": "act.discord_moderate",
    "timeout_member": "act.discord_moderate",
    "set_nickname": "act.discord_moderate",
}
