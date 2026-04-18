/**
 * PersonDetailForm -- create or edit a person in the contacts directory.
 *
 * If the URL has an :id param, loads that person for editing. Otherwise,
 * renders an empty form for creation. On save, POSTs or PUTs to /api/people/.
 * The formToPayload() helper transforms the flat form state into the nested
 * JSON structure the backend expects (contact_info, key_dates, preferences).
 */
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiFetch } from "../../utils/api";
import type { Person } from "../../types/people";
import { inputClass, textareaClass } from "../profile/Section";

const RELATIONSHIP_TYPES = [
  "partner",
  "family",
  "friend",
  "coworker",
  "acquaintance",
  "other",
];

interface FormData {
  name: string;
  relationship_type: string;
  description: string;
  contact_phone: string;
  contact_email: string;
  birthday: string;
  anniversary: string;
  pref_dietary: string;
  pref_gift_ideas: string;
  notes: string;
}

const EMPTY_FORM: FormData = {
  name: "",
  relationship_type: "",
  description: "",
  contact_phone: "",
  contact_email: "",
  birthday: "",
  anniversary: "",
  pref_dietary: "",
  pref_gift_ideas: "",
  notes: "",
};

function personToForm(person: Person): FormData {
  return {
    name: person.name,
    relationship_type: person.relationship_type || "",
    description: person.description || "",
    contact_phone: person.contact_info?.phone || "",
    contact_email: person.contact_info?.email || "",
    birthday: person.key_dates?.birthday || "",
    anniversary: person.key_dates?.anniversary || "",
    pref_dietary: person.preferences?.dietary || "",
    pref_gift_ideas: person.preferences?.gift_ideas || "",
    notes: person.notes || "",
  };
}

function formToPayload(form: FormData) {
  return {
    name: form.name,
    relationship_type: form.relationship_type || null,
    description: form.description || null,
    contact_info:
      form.contact_phone || form.contact_email
        ? {
            ...(form.contact_phone && { phone: form.contact_phone }),
            ...(form.contact_email && { email: form.contact_email }),
          }
        : null,
    key_dates:
      form.birthday || form.anniversary
        ? {
            ...(form.birthday && { birthday: form.birthday }),
            ...(form.anniversary && { anniversary: form.anniversary }),
          }
        : null,
    preferences:
      form.pref_dietary || form.pref_gift_ideas
        ? {
            ...(form.pref_dietary && { dietary: form.pref_dietary }),
            ...(form.pref_gift_ideas && { gift_ideas: form.pref_gift_ideas }),
          }
        : null,
    notes: form.notes || null,
  };
}

export default function PersonDetailForm() {
  const { id } = useParams();
  const navigate = useNavigate();
  const isNew = !id || id === "new";
  const [form, setForm] = useState<FormData>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(isNew);

  useEffect(() => {
    if (!isNew) {
      apiFetch<Person>(`/people/${id}`).then((person) => {
        setForm(personToForm(person));
        setLoaded(true);
      });
    }
  }, [id, isNew]);

  const set = (key: keyof FormData, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleSave = async () => {
    if (!form.name.trim()) {
      setMessage("Error: Name is required");
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const payload = formToPayload(form);
      if (isNew) {
        await apiFetch("/people/", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      } else {
        await apiFetch(`/people/${id}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
      }
      navigate("/profile/people");
    } catch (e) {
      setMessage(`Error: ${e instanceof Error ? e.message : "Unknown error"}`);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm("Are you sure you want to delete this person?")) return;
    await apiFetch(`/people/${id}`, { method: "DELETE" });
    navigate("/profile/people");
  };

  if (!loaded) {
    return <div className="py-12 text-center text-gray-400">Loading...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-800">
          {isNew ? "Add Person" : "Edit Person"}
        </h1>
        <div className="flex gap-2">
          {!isNew && (
            <button
              onClick={handleDelete}
              className="px-4 py-2 text-red-600 border border-red-200 rounded-lg text-sm hover:bg-red-50 transition-colors"
            >
              Delete
            </button>
          )}
          <button
            onClick={() => navigate("/profile/people")}
            className="px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-5 py-2 bg-primary-600 text-white rounded-lg text-sm font-medium hover:bg-primary-700 disabled:opacity-50 transition-colors"
          >
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>

      {message && (
        <div
          className={`px-4 py-2 rounded-lg text-sm ${
            message.startsWith("Error")
              ? "bg-red-50 text-red-700"
              : "bg-green-50 text-green-700"
          }`}
        >
          {message}
        </div>
      )}

      <div className="bg-white rounded-lg border border-gray-200 p-5 space-y-4">
        <h2 className="text-lg font-semibold text-gray-700">Basic Info</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-600 mb-1">
              Name *
            </label>
            <input
              className={inputClass}
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-600 mb-1">
              Relationship
            </label>
            <select
              className={inputClass}
              value={form.relationship_type}
              onChange={(e) => set("relationship_type", e.target.value)}
            >
              <option value="">Select</option>
              {RELATIONSHIP_TYPES.map((rt) => (
                <option key={rt} value={rt} className="capitalize">
                  {rt.charAt(0).toUpperCase() + rt.slice(1)}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-600 mb-1">
            Description
          </label>
          <textarea
            className={textareaClass}
            value={form.description}
            onChange={(e) => set("description", e.target.value)}
            placeholder="How do you know this person?"
          />
        </div>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-5 space-y-4">
        <h2 className="text-lg font-semibold text-gray-700">Contact Info</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-600 mb-1">
              Phone
            </label>
            <input
              className={inputClass}
              value={form.contact_phone}
              onChange={(e) => set("contact_phone", e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-600 mb-1">
              Email
            </label>
            <input
              type="email"
              className={inputClass}
              value={form.contact_email}
              onChange={(e) => set("contact_email", e.target.value)}
            />
          </div>
        </div>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-5 space-y-4">
        <h2 className="text-lg font-semibold text-gray-700">Key Dates</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-600 mb-1">
              Birthday
            </label>
            <input
              type="date"
              className={inputClass}
              value={form.birthday}
              onChange={(e) => set("birthday", e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-600 mb-1">
              Anniversary
            </label>
            <input
              type="date"
              className={inputClass}
              value={form.anniversary}
              onChange={(e) => set("anniversary", e.target.value)}
            />
          </div>
        </div>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-5 space-y-4">
        <h2 className="text-lg font-semibold text-gray-700">Preferences</h2>
        <div>
          <label className="block text-sm font-medium text-gray-600 mb-1">
            Dietary
          </label>
          <input
            className={inputClass}
            value={form.pref_dietary}
            onChange={(e) => set("pref_dietary", e.target.value)}
            placeholder="e.g., vegetarian, no shellfish"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-600 mb-1">
            Gift Ideas
          </label>
          <input
            className={inputClass}
            value={form.pref_gift_ideas}
            onChange={(e) => set("pref_gift_ideas", e.target.value)}
            placeholder="e.g., likes books, enjoys cooking"
          />
        </div>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-5 space-y-4">
        <h2 className="text-lg font-semibold text-gray-700">Notes</h2>
        <textarea
          className={textareaClass}
          value={form.notes}
          onChange={(e) => set("notes", e.target.value)}
          placeholder="Anything else to remember about this person..."
          rows={4}
        />
      </div>
    </div>
  );
}
