// Une section des réglages, d'après l'adresse : un groupe du schéma, Outils ou Personas.
import { Navigate, useOutletContext, useParams } from "react-router-dom";
import GroupSection from "./GroupSection.jsx";
import PersonasSection from "./PersonasSection.jsx";
import ToolsSection from "./ToolsSection.jsx";

export default function SettingsSection() {
  const settings = useOutletContext();
  const { section } = useParams();
  const found = settings.sections.find((s) => s.slug === section);
  if (!found) return <Navigate to="/settings" replace />;
  if (found.label === "Personas") return <PersonasSection settings={settings} />;
  if (found.label === "Outils") return <ToolsSection settings={settings} />;
  return <GroupSection settings={settings} group={found.label} first={found === settings.sections[0]} />;
}
