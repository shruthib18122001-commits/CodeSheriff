import { Link, useParams } from "react-router-dom";

const TABS = [
  { key: "chat", label: "Chat" },
  { key: "architecture", label: "Architecture" },
  { key: "community", label: "Community" },
] as const;

interface Props {
  active: (typeof TABS)[number]["key"];
}

/** Lets a user switch between a repo's Chat / Architecture / Community pages. */
function RepoTabs({ active }: Props) {
  const { repoId } = useParams<{ repoId: string }>();

  return (
    <div className="repo-tabs">
      {TABS.map((t) => (
        <Link
          key={t.key}
          to={`/repo/${repoId}/${t.key}`}
          className={`repo-tab${t.key === active ? " active" : ""}`}
        >
          {t.label}
        </Link>
      ))}
    </div>
  );
}

export default RepoTabs;
