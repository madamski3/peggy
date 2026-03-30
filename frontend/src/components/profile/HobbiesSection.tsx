import Section, { Field } from "./Section";
import TagInput from "./TagInput";

interface Props {
  fields: Record<string, unknown>;
  onChange: (fields: Record<string, unknown>) => void;
}

export default function HobbiesSection({ fields, onChange }: Props) {
  return (
    <Section title="Hobbies & Interests">
      <Field label="Hobbies">
        <TagInput
          tags={(fields.hobbies as string[]) || []}
          onChange={(tags) => onChange({ hobbies: tags })}
          placeholder="e.g., Woodworking, Running, Cooking"
        />
      </Field>
      <Field label="Interests">
        <TagInput
          tags={(fields.interests as string[]) || []}
          onChange={(tags) => onChange({ interests: tags })}
          placeholder="e.g., AI, Space exploration, History"
        />
      </Field>
    </Section>
  );
}
