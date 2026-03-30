import Section, { Field, inputClass } from "./Section";
import TagInput from "./TagInput";

interface Props {
  fields: Record<string, unknown>;
  onChange: (fields: Record<string, unknown>) => void;
}

export default function PreferencesSection({ fields, onChange }: Props) {
  return (
    <Section title="Preferences">
      <Field label="Dietary Likes">
        <TagInput
          tags={(fields.dietary_likes as string[]) || []}
          onChange={(tags) => onChange({ dietary_likes: tags })}
          placeholder="Type and press Enter to add"
        />
      </Field>
      <Field label="Dietary Dislikes">
        <TagInput
          tags={(fields.dietary_dislikes as string[]) || []}
          onChange={(tags) => onChange({ dietary_dislikes: tags })}
          placeholder="Type and press Enter to add"
        />
      </Field>
      <Field label="Communication Style">
        <select
          className={inputClass}
          value={(fields.communication_style as string) || ""}
          onChange={(e) => onChange({ communication_style: e.target.value })}
        >
          <option value="">Select style</option>
          <option value="concise">Concise</option>
          <option value="detailed">Detailed</option>
          <option value="casual">Casual</option>
          <option value="formal">Formal</option>
        </select>
      </Field>
    </Section>
  );
}
