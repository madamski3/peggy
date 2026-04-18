import { useState } from "react";
import Section, { Field, inputClass, textareaClass } from "./Section";
import TagInput from "./TagInput";
import type { Role } from "../../types/profile";
import { generateId } from "../../utils/id";

interface Props {
  fields: Record<string, unknown>;
  onChange: (fields: Record<string, unknown>) => void;
}

function newRole(): Role {
  return {
    id: generateId(),
    name: "",
    title: "",
    employer: "",
    period: "",
    work_arrangement: "",
    experience: [],
    notes: "",
  };
}

function deriveRoleName(role: Role): string {
  const parts = [role.title, role.employer].filter(Boolean);
  return parts.join(" @ ") || "Untitled Role";
}

export default function CareerSection({ fields, onChange }: Props) {
  const roles = (fields.roles as Role[]) || [];
  const [expandedIndex, setExpandedIndex] = useState<number | null>(
    roles.length > 0 ? 0 : null
  );

  const setRoles = (updated: Role[]) => onChange({ roles: updated });

  const addRole = () => {
    const updated = [newRole(), ...roles];
    setRoles(updated);
    setExpandedIndex(0);
  };

  const removeRole = (i: number) => {
    setRoles(roles.filter((_, idx) => idx !== i));
    setExpandedIndex(null);
  };

  const updateRole = (i: number, patch: Partial<Role>) => {
    const updated = [...roles];
    updated[i] = { ...updated[i], ...patch };
    // Auto-derive the name field used as the structured_list key
    updated[i].name = deriveRoleName(updated[i]);
    setRoles(updated);
  };

  return (
    <Section title="Career">
      <div>
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium text-gray-600">Roles</span>
          <button
            type="button"
            onClick={addRole}
            className="text-sm text-primary-600 hover:text-primary-800"
          >
            + Add role
          </button>
        </div>

        {roles.length === 0 && (
          <p className="text-sm text-gray-400 italic">
            No roles added yet. Click &quot;+ Add role&quot; to get started.
          </p>
        )}

        <div className="space-y-2">
          {roles.map((role, i) => {
            const isExpanded = expandedIndex === i;
            const summary = role.title
              ? `${role.title}${role.employer ? ` @ ${role.employer}` : ""}${role.period ? ` (${role.period})` : ""}`
              : "New Role";

            return (
              <div
                key={role.id || i}
                className="border border-gray-200 rounded-lg overflow-hidden"
              >
                {/* Collapsed header */}
                <button
                  type="button"
                  onClick={() => setExpandedIndex(isExpanded ? null : i)}
                  className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-gray-50 transition-colors"
                >
                  <span className="text-sm font-medium text-gray-700 truncate">
                    {summary}
                  </span>
                  <span className="text-gray-400 text-xs ml-2 shrink-0">
                    {isExpanded ? "Collapse" : "Expand"}
                  </span>
                </button>

                {/* Expanded form */}
                {isExpanded && (
                  <div className="px-4 pb-4 space-y-4 border-t border-gray-100 pt-4">
                    <div className="grid grid-cols-2 gap-4">
                      <Field label="Job Title">
                        <input
                          className={inputClass}
                          value={role.title}
                          onChange={(e) =>
                            updateRole(i, { title: e.target.value })
                          }
                          placeholder="e.g., Director of Analytics"
                        />
                      </Field>
                      <Field label="Employer">
                        <input
                          className={inputClass}
                          value={role.employer}
                          onChange={(e) =>
                            updateRole(i, { employer: e.target.value })
                          }
                          placeholder="e.g., Acme Corp"
                        />
                      </Field>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <Field label="Period">
                        <input
                          className={inputClass}
                          value={role.period}
                          onChange={(e) =>
                            updateRole(i, { period: e.target.value })
                          }
                          placeholder="e.g., Jan 2022 – Present"
                        />
                      </Field>
                      <Field label="Work Arrangement">
                        <select
                          className={inputClass}
                          value={role.work_arrangement}
                          onChange={(e) =>
                            updateRole(i, {
                              work_arrangement: e.target.value,
                            })
                          }
                        >
                          <option value="">Select</option>
                          <option value="remote">Remote</option>
                          <option value="hybrid">Hybrid</option>
                          <option value="in-office">In-Office</option>
                        </select>
                      </Field>
                    </div>
                    <Field label="Experience">
                      <TagInput
                        tags={role.experience || []}
                        onChange={(tags) =>
                          updateRole(i, { experience: tags })
                        }
                        placeholder="Type a bullet and press Enter"
                      />
                    </Field>
                    <Field label="Additional Notes">
                      <textarea
                        className={textareaClass}
                        value={role.notes}
                        onChange={(e) =>
                          updateRole(i, { notes: e.target.value })
                        }
                        placeholder="Context about the working environment, team, or anything relevant..."
                        rows={3}
                      />
                    </Field>
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={() => removeRole(i)}
                        className="text-sm text-red-500 hover:text-red-700"
                      >
                        Remove this role
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <Field label="Professional Skills">
        <TagInput
          tags={(fields.professional_skills as string[]) || []}
          onChange={(tags) => onChange({ professional_skills: tags })}
          placeholder="e.g., Python, SQL, Data Modeling"
        />
      </Field>
    </Section>
  );
}
