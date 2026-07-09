import { Activity, Filter, MousePointer2, Network } from "lucide-react";

export default function GraphStatsBar({
  totalNodes = 0,
  totalLinks = 0,
  visibleNodes = 0,
  visibleLinks = 0,
  selectedNode = null,
  activeFilterCount = 0,
}) {
  const items = [
    { icon: Network, label: "Visible Nodes", value: `${visibleNodes}/${totalNodes}` },
    { icon: Activity, label: "Visible Relationships", value: `${visibleLinks}/${totalLinks}` },
    { icon: MousePointer2, label: "Selected Degree", value: selectedNode ? selectedNode.degree || 0 : "none" },
    { icon: Filter, label: "Active Filters", value: activeFilterCount },
  ];

  return (
    <div className="primekg-stats-bar">
      {items.map(({ icon: Icon, label, value }) => (
        <div key={label}>
          <Icon size={15} />
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}
