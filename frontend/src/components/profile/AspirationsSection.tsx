import Section, { Field } from "./Section";
import TagInput from "./TagInput";

interface Props {
  fields: Record<string, unknown>;
  onChange: (fields: Record<string, unknown>) => void;
}

export default function AspirationsSection({ fields, onChange }: Props) {
  return (
    <Section title="Aspirations">
      <Field label="Life Goals / Aspirations">
        <TagInput
          tags={(fields.aspirations as string[]) || []}
          onChange={(tags) => onChange({ aspirations: tags })}
          placeholder="e.g., Get healthier, Build long-term wealth"
        />
      </Field>
    </Section>
  );
}
