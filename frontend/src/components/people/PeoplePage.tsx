/**
 * PeoplePage -- lists all contacts with optional relationship type filtering.
 *
 * Fetches people from GET /api/people/ and renders them as clickable cards
 * (PersonList). Relationship type filter buttons are dynamically generated
 * from the data. Links to PersonDetailForm for create/edit.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../../utils/api";
import type { Person } from "../../types/people";
import PersonList from "./PersonList";

export default function PeoplePage() {
  const [people, setPeople] = useState<Person[]>([]);
  const [filter, setFilter] = useState("");
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const params = filter ? `?relationship=${encodeURIComponent(filter)}` : "";
    apiFetch<{ people: Person[] }>(`/people/${params}`).then((data) => {
      setPeople(data.people);
      setLoaded(true);
    });
  }, [filter]);

  if (!loaded) {
    return <div className="py-12 text-center text-gray-400">Loading...</div>;
  }

  const relationshipTypes = [
    ...new Set(
      people.map((p) => p.relationship_type).filter(Boolean) as string[]
    ),
  ].sort();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-800">People</h1>
        <Link
          to="/profile/people/new"
          className="px-4 py-2 bg-primary-600 text-white rounded-lg text-sm font-medium hover:bg-primary-700 transition-colors"
        >
          + Add Person
        </Link>
      </div>

      {relationshipTypes.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={() => setFilter("")}
            className={`px-3 py-1 rounded-full text-sm ${
              filter === ""
                ? "bg-primary-100 text-primary-700"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            All
          </button>
          {relationshipTypes.map((rt) => (
            <button
              key={rt}
              onClick={() => setFilter(rt)}
              className={`px-3 py-1 rounded-full text-sm capitalize ${
                filter === rt
                  ? "bg-primary-100 text-primary-700"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {rt}
            </button>
          ))}
        </div>
      )}

      <PersonList people={people} />
    </div>
  );
}
