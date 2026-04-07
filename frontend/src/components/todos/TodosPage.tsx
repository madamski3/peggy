import { useEffect, useState } from "react";
import { apiFetch } from "../../utils/api";
import type { Todo } from "../../types/todos";

const STATUS_OPTIONS = ["backlog", "scheduled", "completed", "cancelled"];
const STATUS_FILTERS = ["all", ...STATUS_OPTIONS];
const PRIORITY_COLORS: Record<string, string> = {
  urgent: "bg-red-100 text-red-700",
  high: "bg-orange-100 text-orange-700",
  medium: "bg-blue-100 text-blue-700",
  low: "bg-gray-100 text-gray-600",
};
const STATUS_COLORS: Record<string, string> = {
  backlog: "bg-gray-100 text-gray-600",
  scheduled: "bg-blue-100 text-blue-700",
  completed: "bg-green-100 text-green-700",
  cancelled: "bg-gray-100 text-gray-500",
};

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString();
}

function formatTime(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function TodosPage() {
  const [todos, setTodos] = useState<Todo[]>([]);
  const [filter, setFilter] = useState("all");
  const [loaded, setLoaded] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const params = filter !== "all" ? `?status=${filter}` : "";
    apiFetch<{ todos: Todo[] }>(`/todos/${params}`).then((data) => {
      setTodos(data.todos);
      setLoaded(true);
    });
  }, [filter, refreshKey]);

  async function handleStatusChange(id: string, newStatus: string) {
    await apiFetch(`/todos/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: newStatus }),
    });
    setRefreshKey((k) => k + 1);
  }

  async function handleDelete(id: string, title: string) {
    if (!confirm(`Delete "${title}" and all its sub-items?`)) return;
    await apiFetch(`/todos/${id}`, { method: "DELETE" });
    setRefreshKey((k) => k + 1);
  }

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
                <th className="px-4 py-3">Scheduled</th>
                <th className="px-4 py-3">Deadline</th>
                <th className="px-4 py-3">Duration</th>
                <th className="px-4 py-3 w-10"></th>
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
                    <select
                      value={todo.status}
                      onChange={(e) => handleStatusChange(todo.id, e.target.value)}
                      className={`px-2 py-0.5 rounded text-xs capitalize appearance-none cursor-pointer border-0 ${
                        STATUS_COLORS[todo.status] || "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {STATUS_OPTIONS.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
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
                    {todo.scheduled_start
                      ? `${formatDate(todo.scheduled_start)} ${formatTime(todo.scheduled_start)}`
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {formatDate(todo.deadline)}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {todo.estimated_duration_minutes
                      ? `${todo.estimated_duration_minutes}m`
                      : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => handleDelete(todo.id, todo.title)}
                      className="text-gray-300 hover:text-red-500 transition-colors"
                      title="Delete todo"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
                      </svg>
                    </button>
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
