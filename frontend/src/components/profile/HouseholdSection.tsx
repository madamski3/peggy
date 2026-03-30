import { useState } from "react";
import Section, { Field, inputClass, textareaClass } from "./Section";
import TagInput from "./TagInput";
import type { Pet, Vehicle } from "../../types/profile";
import { generateId } from "../../utils/id";

interface Props {
  fields: Record<string, unknown>;
  onChange: (fields: Record<string, unknown>) => void;
}

function newPet(): Pet {
  return {
    id: generateId(),
    name: "",
    species: "",
    date_of_birth: "",
    sex: "",
    likes_dislikes: "",
    notes: "",
  };
}

function newVehicle(): Vehicle {
  return {
    id: generateId(),
    name: "",
    year: "",
    make: "",
    model: "",
    vin: "",
    mileage: "",
    purchase_date: "",
    license_plate: "",
    history: [],
  };
}

function deriveVehicleName(v: Vehicle): string {
  const parts = [v.year, v.make, v.model].filter(Boolean);
  return parts.join(" ") || "New Vehicle";
}

export default function HouseholdSection({ fields, onChange }: Props) {
  const pets = (fields.pets as Pet[]) || [];
  const vehicles = (fields.vehicles as Vehicle[]) || [];
  const [expandedPet, setExpandedPet] = useState<number | null>(null);
  const [expandedVehicle, setExpandedVehicle] = useState<number | null>(null);

  const setPets = (updated: Pet[]) => onChange({ pets: updated });
  const setVehicles = (updated: Vehicle[]) => onChange({ vehicles: updated });

  const addPet = () => {
    const updated = [newPet(), ...pets];
    setPets(updated);
    setExpandedPet(0);
  };
  const removePet = (i: number) => {
    setPets(pets.filter((_, idx) => idx !== i));
    setExpandedPet(null);
  };
  const updatePet = (i: number, patch: Partial<Pet>) => {
    const updated = [...pets];
    updated[i] = { ...updated[i], ...patch };
    setPets(updated);
  };

  const addVehicle = () => {
    const updated = [newVehicle(), ...vehicles];
    setVehicles(updated);
    setExpandedVehicle(0);
  };
  const removeVehicle = (i: number) => {
    setVehicles(vehicles.filter((_, idx) => idx !== i));
    setExpandedVehicle(null);
  };
  const updateVehicle = (i: number, patch: Partial<Vehicle>) => {
    const updated = [...vehicles];
    updated[i] = { ...updated[i], ...patch };
    // Auto-derive name for display
    updated[i].name = deriveVehicleName(updated[i]);
    setVehicles(updated);
  };
  const updateVehicleHistory = (i: number, history: string[]) => {
    const updated = [...vehicles];
    updated[i] = { ...updated[i], history };
    setVehicles(updated);
  };

  return (
    <Section title="Household">
      <Field label="Partner Name">
        <input
          className={inputClass}
          value={(fields.partner_name as string) || ""}
          onChange={(e) => onChange({ partner_name: e.target.value })}
        />
      </Field>

      {/* Pets */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium text-gray-600">Pets</span>
          <button
            type="button"
            onClick={addPet}
            className="text-sm text-blue-600 hover:text-blue-800"
          >
            + Add pet
          </button>
        </div>

        {pets.length === 0 && (
          <p className="text-sm text-gray-400 italic">
            No pets added yet.
          </p>
        )}

        <div className="space-y-2">
          {pets.map((pet, i) => {
            const isExpanded = expandedPet === i;
            const summary = pet.name
              ? `${pet.name}${pet.species ? ` (${pet.species})` : ""}`
              : "New Pet";

            return (
              <div
                key={pet.id || i}
                className="border border-gray-200 rounded-lg overflow-hidden"
              >
                <button
                  type="button"
                  onClick={() => setExpandedPet(isExpanded ? null : i)}
                  className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-gray-50 transition-colors"
                >
                  <span className="text-sm font-medium text-gray-700 truncate">
                    {summary}
                  </span>
                  <span className="text-gray-400 text-xs ml-2 shrink-0">
                    {isExpanded ? "Collapse" : "Expand"}
                  </span>
                </button>

                {isExpanded && (
                  <div className="px-4 pb-4 space-y-4 border-t border-gray-100 pt-4">
                    <div className="grid grid-cols-2 gap-4">
                      <Field label="Name">
                        <input
                          className={inputClass}
                          value={pet.name}
                          onChange={(e) =>
                            updatePet(i, { name: e.target.value })
                          }
                          placeholder="e.g., Mochi"
                        />
                      </Field>
                      <Field label="Species">
                        <input
                          className={inputClass}
                          value={pet.species}
                          onChange={(e) =>
                            updatePet(i, { species: e.target.value })
                          }
                          placeholder="e.g., Dog, Cat"
                        />
                      </Field>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <Field label="Date of Birth">
                        <input
                          type="date"
                          className={inputClass}
                          value={pet.date_of_birth}
                          onChange={(e) =>
                            updatePet(i, { date_of_birth: e.target.value })
                          }
                        />
                      </Field>
                      <Field label="Sex">
                        <select
                          className={inputClass}
                          value={pet.sex}
                          onChange={(e) =>
                            updatePet(i, { sex: e.target.value })
                          }
                        >
                          <option value="">Select</option>
                          <option value="male">Male</option>
                          <option value="female">Female</option>
                        </select>
                      </Field>
                    </div>
                    <Field label="Likes / Dislikes">
                      <textarea
                        className={textareaClass}
                        value={pet.likes_dislikes}
                        onChange={(e) =>
                          updatePet(i, { likes_dislikes: e.target.value })
                        }
                        placeholder="e.g., Loves belly rubs, hates the vacuum..."
                        rows={2}
                      />
                    </Field>
                    <Field label="Other Notes">
                      <textarea
                        className={textareaClass}
                        value={pet.notes}
                        onChange={(e) =>
                          updatePet(i, { notes: e.target.value })
                        }
                        placeholder="e.g., Allergies, medications, vet info..."
                        rows={2}
                      />
                    </Field>
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={() => removePet(i)}
                        className="text-sm text-red-500 hover:text-red-700"
                      >
                        Remove this pet
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Vehicles */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium text-gray-600">Vehicles</span>
          <button
            type="button"
            onClick={addVehicle}
            className="text-sm text-blue-600 hover:text-blue-800"
          >
            + Add vehicle
          </button>
        </div>

        {vehicles.length === 0 && (
          <p className="text-sm text-gray-400 italic">
            No vehicles added yet.
          </p>
        )}

        <div className="space-y-2">
          {vehicles.map((v, i) => {
            const isExpanded = expandedVehicle === i;
            const summary = deriveVehicleName(v);

            return (
              <div
                key={v.id || i}
                className="border border-gray-200 rounded-lg overflow-hidden"
              >
                <button
                  type="button"
                  onClick={() =>
                    setExpandedVehicle(isExpanded ? null : i)
                  }
                  className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-gray-50 transition-colors"
                >
                  <span className="text-sm font-medium text-gray-700 truncate">
                    {summary}
                  </span>
                  <span className="text-gray-400 text-xs ml-2 shrink-0">
                    {isExpanded ? "Collapse" : "Expand"}
                  </span>
                </button>

                {isExpanded && (
                  <div className="px-4 pb-4 space-y-4 border-t border-gray-100 pt-4">
                    <div className="grid grid-cols-3 gap-4">
                      <Field label="Year">
                        <input
                          className={inputClass}
                          value={v.year}
                          onChange={(e) =>
                            updateVehicle(i, { year: e.target.value })
                          }
                          placeholder="e.g., 2023"
                        />
                      </Field>
                      <Field label="Make">
                        <input
                          className={inputClass}
                          value={v.make}
                          onChange={(e) =>
                            updateVehicle(i, { make: e.target.value })
                          }
                          placeholder="e.g., Honda"
                        />
                      </Field>
                      <Field label="Model">
                        <input
                          className={inputClass}
                          value={v.model}
                          onChange={(e) =>
                            updateVehicle(i, { model: e.target.value })
                          }
                          placeholder="e.g., Civic"
                        />
                      </Field>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <Field label="VIN">
                        <input
                          className={inputClass}
                          value={v.vin}
                          onChange={(e) =>
                            updateVehicle(i, { vin: e.target.value })
                          }
                          placeholder="e.g., 1HGBH41JXMN109186"
                        />
                      </Field>
                      <Field label="License Plate">
                        <input
                          className={inputClass}
                          value={v.license_plate}
                          onChange={(e) =>
                            updateVehicle(i, {
                              license_plate: e.target.value,
                            })
                          }
                          placeholder="e.g., ABC 1234"
                        />
                      </Field>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <Field label="Mileage">
                        <input
                          className={inputClass}
                          value={v.mileage}
                          onChange={(e) =>
                            updateVehicle(i, { mileage: e.target.value })
                          }
                          placeholder="e.g., 45,000"
                        />
                      </Field>
                      <Field label="Purchase Date">
                        <input
                          type="date"
                          className={inputClass}
                          value={v.purchase_date}
                          onChange={(e) =>
                            updateVehicle(i, {
                              purchase_date: e.target.value,
                            })
                          }
                        />
                      </Field>
                    </div>
                    <Field label="History">
                      <TagInput
                        tags={v.history || []}
                        onChange={(tags) => updateVehicleHistory(i, tags)}
                        placeholder="e.g., Oil change 3/15/2026, New tires 1/10/2026"
                      />
                    </Field>
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={() => removeVehicle(i)}
                        className="text-sm text-red-500 hover:text-red-700"
                      >
                        Remove this vehicle
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
