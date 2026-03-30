import Section, { Field, inputClass, textareaClass } from "./Section";

const TIMEZONES = [
  "America/Los_Angeles",
  "America/Denver",
  "America/Chicago",
  "America/New_York",
  "America/Phoenix",
  "America/Anchorage",
  "Pacific/Honolulu",
  "UTC",
];

interface Props {
  fields: Record<string, unknown>;
  onChange: (fields: Record<string, unknown>) => void;
}

export default function IdentitySection({ fields, onChange }: Props) {
  const set = (key: string, value: string) => onChange({ [key]: value });

  return (
    <Section title="Identity">
      <div className="grid grid-cols-2 gap-4">
        <Field label="Name">
          <input
            className={inputClass}
            value={(fields.name as string) || ""}
            onChange={(e) => set("name", e.target.value)}
          />
        </Field>
        <Field label="Date of Birth">
          <input
            type="date"
            className={inputClass}
            value={(fields.date_of_birth as string) || ""}
            onChange={(e) => set("date_of_birth", e.target.value)}
          />
        </Field>
      </div>
      <Field label="Location">
        <input
          className={inputClass}
          value={(fields.location as string) || ""}
          onChange={(e) => set("location", e.target.value)}
          placeholder="e.g., Camas, WA (Portland metro)"
        />
      </Field>
      <Field label="Timezone">
        <select
          className={inputClass}
          value={(fields.timezone as string) || ""}
          onChange={(e) => set("timezone", e.target.value)}
        >
          <option value="">Select timezone</option>
          {TIMEZONES.map((tz) => (
            <option key={tz} value={tz}>
              {tz}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Living Situation">
        <textarea
          className={textareaClass}
          value={(fields.living_situation as string) || ""}
          onChange={(e) => set("living_situation", e.target.value)}
          placeholder="e.g., Lives with partner in house"
        />
      </Field>
    </Section>
  );
}
