import { useEffect, useState } from "react";
import { apiFetch } from "../../utils/api";
import type { Todo } from "../../types/todos";

const STATUS_FILTERS = ["all", "backlog", "active", "completed", "cancelled"];
const PRIORITY_COLORS: Record<string, string> = {
  urgent: "bg-red-100 text-red-700",
  high: "bg-orange-100 text-orange-700",
  medium: "bg-blue-100 text-blue-700",
  low: "bg-gray-100 text-gray-600",
};

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString();
}

export default function TodosPage() {
  const [todos, setTodos] = useState<Todo[]>([]);
  const [filter, setFilter] = useState("all");
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const params = filter !== "all" ? `?status=${filter}` : "";
    apiFetch<{ todos: Todo[] }>(`/todos/${params}`).then((data) => {
      setTodos(data.todos);
      setLoaded(true);
    });
  }, [filter]);

  if (!loaded) {
    return <div className="py-12 text-center text-gray-400">Loading...</div>;
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-gray-800">Todos</h1>

      <div className="flex gap-2 flex-wrap">
        {STATUS_FILTERS.map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`px-3 py-1 rounded-full text-sm capitalize ${
              filter === s
                ? "bg-blue-100 text-blue-700"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {todos.length === 0 ? (
        <div className="py-8 text-center text-gray-400 text-sm">
          No todos found.
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left text-gray-500 text-xs uppercase tracking-wider">
                <th className="px-4 py-3">Title</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Priority</th>
                <th className="px-4 py-3">Deadline</th>
                <th className="px-4 py-3">Duration</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {todos.map((todo) => (
                <tr key={todo.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-gray-800 font-medium">
                    {todo.title}
                    {todo.tags && todo.tags.length > 0 && (
                      <span className="ml-2 text-xs text-gray-400">
                        {todo.tags.join(", ")}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className="inline-block px-2 py-0.5 rounded text-xs capitalize bg-gray-100 text-gray-600">
                      {todo.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block px-2 py-0.5 rounded text-xs capitalize ${
                        PRIORITY_COLORS[todo.priority] || "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {todo.priority}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {formatDate(todo.deadline)}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {todo.estimated_duration_minutes
                      ? `${todo.estimated_duration_minutes}m`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
