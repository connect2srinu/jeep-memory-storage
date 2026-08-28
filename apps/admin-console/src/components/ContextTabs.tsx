
export function ContextTabs<T extends string>({ tabs, selected, onSelect }: { tabs: Array<[T, string]>; selected: T; onSelect: (tab: T) => void }) {
  return <div className="context-tabs" role="tablist">{tabs.map(([id, label]) => <button type="button" role="tab" aria-selected={selected === id} className={selected === id ? "active" : ""} key={id} onClick={() => onSelect(id)}>{label}</button>)}</div>;
}

