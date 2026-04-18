import { useState } from "react";
import Section, { Field, inputClass } from "./Section";
import type { Contact } from "../../types/profile";
import { generateId } from "../../utils/id";

interface Props {
  fields: Record<string, unknown>;
  onChange: (fields: Record<string, unknown>) => void;
}

function newContact(): Contact {
  return {
    id: generateId(),
    name: "",
    type: "email",
    description: "",
    value: "",
    primary: false,
  };
}

function deriveContactName(contact: Contact): string {
  const parts = [contact.type, contact.description].filter(Boolean);
  return parts.join(" - ") || "New Contact";
}

export default function ContactSection({ fields, onChange }: Props) {
  const contacts = (fields.contacts as Contact[]) || [];
  const [expandedIndex, setExpandedIndex] = useState<number | null>(
    contacts.length > 0 ? 0 : null
  );

  const setContacts = (updated: Contact[]) => onChange({ contacts: updated });

  const addContact = () => {
    const updated = [newContact(), ...contacts];
    setContacts(updated);
    setExpandedIndex(0);
  };

  const removeContact = (i: number) => {
    setContacts(contacts.filter((_, idx) => idx !== i));
    setExpandedIndex(null);
  };

  const updateContact = (i: number, patch: Partial<Contact>) => {
    const updated = [...contacts];
    updated[i] = { ...updated[i], ...patch };
    updated[i].name = deriveContactName(updated[i]);

    // Enforce one-primary-per-type: if this contact was just marked primary,
    // clear primary on all other contacts of the same type.
    if (patch.primary) {
      const contactType = updated[i].type;
      for (let j = 0; j < updated.length; j++) {
        if (j !== i && updated[j].type === contactType && updated[j].primary) {
          updated[j] = { ...updated[j], primary: false };
        }
      }
    }

    setContacts(updated);
  };

  return (
    <Section title="Contact Details">
      <div>
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium text-gray-600">
            Email & Phone
          </span>
          <button
            type="button"
            onClick={addContact}
            className="text-sm text-primary-600 hover:text-primary-800"
          >
            + Add contact
          </button>
        </div>

        {contacts.length === 0 && (
          <p className="text-sm text-gray-400 italic">
            No contacts added yet. Click &quot;+ Add contact&quot; to get
            started.
          </p>
        )}

        <div className="space-y-2">
          {contacts.map((contact, i) => {
            const isExpanded = expandedIndex === i;
            const summary = contact.value
              ? `${contact.description || contact.type}:  ${contact.value}`
              : "New Contact";

            return (
              <div
                key={contact.id || i}
                className="border border-gray-200 rounded-lg overflow-hidden"
              >
                {/* Collapsed header */}
                <button
                  type="button"
                  onClick={() => setExpandedIndex(isExpanded ? null : i)}
                  className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-gray-50 transition-colors"
                >
                  <span className="text-sm font-medium text-gray-700 truncate flex items-center gap-2">
                    <span className="text-gray-400">
                      {contact.type === "phone" ? "\u260E" : "\u2709"}
                    </span>
                    {summary}
                    {contact.primary && (
                      <span className="text-xs bg-primary-100 text-primary-700 px-1.5 py-0.5 rounded font-medium">
                        Primary
                      </span>
                    )}
                  </span>
                  <span className="text-gray-400 text-xs ml-2 shrink-0">
                    {isExpanded ? "Collapse" : "Expand"}
                  </span>
                </button>

                {/* Expanded form */}
                {isExpanded && (
                  <div className="px-4 pb-4 space-y-4 border-t border-gray-100 pt-4">
                    <div className="grid grid-cols-2 gap-4">
                      <Field label="Type">
                        <select
                          className={inputClass}
                          value={contact.type}
                          onChange={(e) =>
                            updateContact(i, { type: e.target.value })
                          }
                        >
                          <option value="email">Email</option>
                          <option value="phone">Phone</option>
                        </select>
                      </Field>
                      <Field label="Description">
                        <input
                          className={inputClass}
                          value={contact.description}
                          onChange={(e) =>
                            updateContact(i, { description: e.target.value })
                          }
                          placeholder="e.g., personal, work"
                        />
                      </Field>
                    </div>
                    <Field label="Value">
                      <input
                        className={inputClass}
                        value={contact.value}
                        onChange={(e) =>
                          updateContact(i, { value: e.target.value })
                        }
                        placeholder={
                          contact.type === "phone"
                            ? "e.g., (555) 123-4567"
                            : "e.g., me@example.com"
                        }
                      />
                    </Field>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={contact.primary}
                        onChange={(e) =>
                          updateContact(i, { primary: e.target.checked })
                        }
                        className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                      />
                      <span className="text-sm text-gray-700">
                        Primary {contact.type}
                      </span>
                      <span className="text-xs text-gray-400">
                        (used by the assistant for calendar & email)
                      </span>
                    </label>
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={() => removeContact(i)}
                        className="text-sm text-red-500 hover:text-red-700"
                      >
                        Remove this contact
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </Section>
  );
}
