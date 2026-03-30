/**
 * ProfilePage -- form-based editor for the user's profile.
 *
 * On mount, loads the current profile via GET /api/profile/ and populates
 * section-specific form components (Identity, Household, Preferences, etc.).
 * On save, flattens all section fields into a single list and POSTs to
 * /api/profile/, which triggers the backend ingestion pipeline to generate
 * ProfileFacts for the agent.
 *
 * State is managed locally (no global store). Each section component receives
 * its fields and an onChange callback to update the parent state.
 */
import { useEffect, useState } from "react";
import { apiFetch } from "../../utils/api";
import type { ProfileData } from "../../types/profile";
import IdentitySection from "./IdentitySection";
import HouseholdSection from "./HouseholdSection";
import PreferencesSection from "./PreferencesSection";
import CareerSection from "./CareerSection";
import HobbiesSection from "./HobbiesSection";
import AspirationsSection from "./AspirationsSection";
import ScheduleSection from "./ScheduleSection";

const EMPTY_PROFILE: ProfileData = {
  identity: { fields: {} },
  household: { fields: {} },
  preferences: { fields: {} },
  career: { fields: {} },
  hobbies: { fields: {} },
  aspirations: { fields: {} },
  schedule: { fields: {} },
};

export default function ProfilePage() {
  const [profile, setProfile] = useState<ProfileData>(EMPTY_PROFILE);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    apiFetch<ProfileData>("/profile/").then((data) => {
      setProfile(data);
      setLoaded(true);
    });
  }, []);

  const updateSection = (
    section: keyof ProfileData,
    fields: Record<string, unknown>
  ) => {
    setProfile((prev) => ({
      ...prev,
      [section]: { fields: { ...prev[section].fields, ...fields } },
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      // Flatten all sections into a field list
      const allFields: { field_key: string; value: unknown }[] = [];
      for (const section of Object.values(profile)) {
        for (const [key, value] of Object.entries(section.fields)) {
          if (value !== null && value !== undefined && value !== "") {
            allFields.push({ field_key: key, value });
          }
        }
      }
      const result = await apiFetch<{ success: boolean; facts_created: number }>(
        "/profile/",
        {
          method: "POST",
          body: JSON.stringify({ fields: allFields }),
        }
      );
      setMessage(
        result.facts_created > 0
          ? `Saved! ${result.facts_created} fact(s) updated.`
          : "No changes detected."
      );
    } catch (e) {
      setMessage(`Error: ${e instanceof Error ? e.message : "Unknown error"}`);
    } finally {
      setSaving(false);
    }
  };

  if (!loaded) {
    return <div className="py-12 text-center text-gray-400">Loading...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-800">Profile</h1>
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-5 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {saving ? "Saving..." : "Save"}
        </button>
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

      <IdentitySection
        fields={profile.identity.fields}
        onChange={(f) => updateSection("identity", f)}
      />
      <HouseholdSection
        fields={profile.household.fields}
        onChange={(f) => updateSection("household", f)}
      />
      <PreferencesSection
        fields={profile.preferences.fields}
        onChange={(f) => updateSection("preferences", f)}
      />
      <CareerSection
        fields={profile.career.fields}
        onChange={(f) => updateSection("career", f)}
      />
      <HobbiesSection
        fields={profile.hobbies.fields}
        onChange={(f) => updateSection("hobbies", f)}
      />
      <AspirationsSection
        fields={profile.aspirations.fields}
        onChange={(f) => updateSection("aspirations", f)}
      />
      <ScheduleSection
        fields={profile.schedule.fields}
        onChange={(f) => updateSection("schedule", f)}
      />
    </div>
  );
}
