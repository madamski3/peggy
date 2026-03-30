import { Link } from "react-router-dom";
import type { Person } from "../../types/people";

interface Props {
  people: Person[];
}

export default function PersonList({ people }: Props) {
  if (people.length === 0) {
    return (
      <div className="py-12 text-center text-gray-400">
        No people added yet.
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      {people.map((person) => (
        <Link
          key={person.id}
          to={`/people/${person.id}`}
          className="block bg-white rounded-lg border border-gray-200 p-4 hover:border-blue-300 hover:shadow-sm transition-all"
        >
          <div className="flex items-center justify-between">
            <div>
              <div className="font-medium text-gray-800">{person.name}</div>
              {person.relationship_type && (
                <div className="text-sm text-gray-500 capitalize">
                  {person.relationship_type}
                </div>
              )}
            </div>
            {person.key_dates?.birthday && (
              <div className="text-sm text-gray-400">
                Birthday: {person.key_dates.birthday}
              </div>
            )}
          </div>
          {person.description && (
            <div className="text-sm text-gray-500 mt-1 line-clamp-1">
              {person.description}
            </div>
          )}
        </Link>
      ))}
    </div>
  );
}
