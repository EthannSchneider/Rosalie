"""Système : lancer une commande shell sur l'ordinateur de son créateur, SANS confirmation.

Voulu : contrairement aux blocs ```run-bash (libs/assistant/code_runner.py), la commande tourne
directement. Garde-fous restants : permission act.code, réglage code_exec, dossier
storages/workspace, délai code_timeout, secrets retirés de l'environnement.
"""
from libs.assistant.code_runner import CodeBlock, run_code
from libs.assistant.tools.base import ToolContext, ToolError, tool, _int
from libs.log import Log


@tool("run_command",
      "Exécute une commande shell (bash) sur l'ordinateur de ton créateur, dans ton dossier de "
      "travail. Renvoie la sortie et le code de sortie. Pas de commande "
      "interactive ni de serveur qui tourne en continu.",
      {"command": ("string", "La commande bash, ex : « ls -la » ou « df -h »"),
       "timeout": ("integer", "Durée max en secondes (défaut : réglage code_timeout)")},
      required=("command",))
async def run_command(ctx: ToolContext, command: str, timeout: int | None = None) -> str:
    config = ctx.config
    if not config.code_exec:
        raise ToolError("l'exécution de code est désactivée (réglage code_exec)")
    command = str(command).strip()
    if not command:
        raise ToolError("commande vide")
    limit = _int(timeout, config.code_timeout, 1, config.code_timeout)

    Log.command(f"run_command ({len(command)} caractères, sans confirmation)")
    result = await run_code(CodeBlock("bash", command, "", ""),
                            config.storage_dir / "workspace", limit)
    Log.info(f"Commande : {result.summary()}")
    # Un code de sortie non nul n'est pas forcément une panne (grep sans résultat → 1) :
    # on renvoie tout au modèle, qui juge.
    return f"{result.summary()}\nSortie :\n{result.output or '(aucune sortie)'}"
