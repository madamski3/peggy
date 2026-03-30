interface Props {
  suggestions: string[];
  onSelect: (text: string) => void;
  disabled?: boolean;
}

export default function FollowUpChips({
  suggestions,
  onSelect,
  disabled,
}: Props) {
  if (suggestions.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2 mt-3">
      {suggestions.map((s) => (
        <button
          key={s}
          type="button"
          onClick={() => onSelect(s)}
          disabled={disabled}
          className="rounded-full border border-gray-300 bg-white px-3 py-1 text-xs text-gray-600 hover:bg-gray-50 hover:border-gray-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {s}
        </button>
      ))}
    </div>
  );
}
