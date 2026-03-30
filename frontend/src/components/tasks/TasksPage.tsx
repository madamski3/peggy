import { useEffect, useState } from "react";
import { apiFetch } from "../../utils/api";
import type { Task } from "../../types/todos";

const STATUS_FILTERS = ["all", "scheduled", "in_progress", "completed", "cancelled"];
const STATUS_COLORS: Record<string, string> = {
  scheduled: "bg-blue-100 text-blue-700",
  in_progress: "bg-yellow-100 text-yellow-700",
  completed: "bg-green-100 text-green-700",
  cancelled: "bg-gray-100 text-gray-500",
};

function formatDateTime(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [filter, setFilter] = useState("all");
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const params = filter !== "all" ? `?status=${filter}` : "";
    apiFetch<{ tasks: Task[] }>(`/tasks/${params}`).then((data) => {
      setTasks(data.tasks);
      setLoaded(true);
    });
  }, [filter]);

  if (!loaded) {
    return <div className="py-12 text-center text-gray-400">Loading...</div>;
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-gray-800">Tasks</h1>

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
            {s === "in_progress" ? "In Progress" : s}
          </button>
        ))}
      </div>

      {tasks.length === 0 ? (
        <div className="py-8 text-center text-gray-400 text-sm">
          No tasks found.
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left text-gray-500 text-xs uppercase tracking-wider">
                <th className="px-4 py-3">Title</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Scheduled Start</th>
                <th className="px-4 py-3">Scheduled End</th>
                <th className="px-4 py-3">Duration</th>
                <th className="px-4 py-3">Deferred</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {tasks.map((task) => (
                <tr key={task.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-gray-800 font-medium">
                    {task.title}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block px-2 py-0.5 rounded text-xs capitalize ${
                        STATUS_COLORS[task.status] || "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {task.status.replace("_", " ")}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {formatDateTime(task.scheduled_start)}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {formatDateTime(task.scheduled_end)}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {task.estimated_duration_minutes
                      ? `${task.estimated_duration_minutes}m`
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {task.deferred_count > 0 ? task.deferred_count : "—"}
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
