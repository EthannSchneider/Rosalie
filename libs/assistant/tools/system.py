"""Système : lancer une commande shell sur l'ordinateur de son créateur, SANS confirmation.

Voulu : contrairement aux blocs ```run-bash (libs/assistant/code_runner.py), la commande tourne
directement. Garde-fous restants : permission act.code, réglage code_exec, dossier
storages/workspace, délai code_timeout, secrets retirés de l'environnement.
"""
from libs.assistant.code_runner import CodeBlock, run_code
from libs.assistant.tools.base import ToolContext, ToolError, result_budget, tool, _int
from libs.log import Log

# Part du contexte pour une sortie (les ~38 schémas d'outils en prennent déjà une bonne partie)
OUTPUT_SHARE = 0.2


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
    # Sortie à la taille du contexte (≠ 3000 caractères des blocs run-bash) : un `cat` coupé au
    # milieu, le modèle le relançait en boucle en espérant voir la suite.
    result = await run_code(CodeBlock("bash", command, "", ""),
                            config.storage_dir / "workspace", limit,
                            output_chars=result_budget(ctx, OUTPUT_SHARE))
    Log.info(f"Commande : {result.summary()}")
    text = f"{result.summary()}\nSortie :\n{result.output or '(aucune sortie)'}"
    if "caractères coupés) …" in result.output:
        text += ("\n(Sortie coupée au milieu : relancer la même commande donnera la même chose. "
                 "Pour un gros fichier, lis-le par morceaux : sed -n '1,120p' fichier, puis "
                 "'121,240p'… ; ou filtre avec grep / head / tail.)")
    # Un code de sortie non nul n'est pas forcément une panne (grep sans résultat → 1) :
    # on renvoie tout au modèle, qui juge.
    return text
