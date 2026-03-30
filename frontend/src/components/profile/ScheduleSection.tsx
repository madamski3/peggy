import Section, { Field, inputClass } from "./Section";

interface Props {
  fields: Record<string, unknown>;
  onChange: (fields: Record<string, unknown>) => void;
}

export default function ScheduleSection({ fields, onChange }: Props) {
  return (
    <Section title="Schedule">
      <Field label="Waking Hours">
        <input
          className={inputClass}
          value={(fields.waking_hours as string) || ""}
          onChange={(e) => onChange({ waking_hours: e.target.value })}
          placeholder="e.g., 7:00 AM - 11:00 PM"
        />
      </Field>
      <Field label="Preferred Work Hours">
        <input
          className={inputClass}
          value={(fields.preferred_work_hours as string) || ""}
          onChange={(e) => onChange({ preferred_work_hours: e.target.value })}
          placeholder="e.g., 9:00 AM - 5:00 PM"
        />
      </Field>
      <Field label="Preferred Errand Time">
        <select
          className={inputClass}
          value={(fields.preferred_errand_time as string) || ""}
          onChange={(e) => onChange({ preferred_errand_time: e.target.value })}
        >
          <option value="">Select</option>
          <option value="early morning">Early Morning</option>
          <option value="late morning">Late Morning</option>
          <option value="afternoon">Afternoon</option>
          <option value="evening">Evening</option>
          <option value="weekend">Weekend</option>
        </select>
      </Field>
    </Section>
  );
}
