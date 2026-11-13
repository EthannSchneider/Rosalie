import { cardClass } from "./styles.js";

export default function Card({ className = "", as: Tag = "section", ...props }) {
  return <Tag className={`${cardClass} ${className}`} {...props} />;
}
