import { Navigate, Route, Routes, useParams } from "react-router-dom";
import Sidebar from "./components/layout/Sidebar";
import ChatPage from "./components/chat/ChatPage";
import ProfilePage from "./components/profile/ProfilePage";
import PeoplePage from "./components/people/PeoplePage";
import PersonDetailForm from "./components/people/PersonDetailForm";
import TodosPage from "./components/todos/TodosPage";
import PlanningPage from "./components/planning/PlanningPage";
import CalendarPage from "./components/calendar/CalendarPage";

function PersonIdRedirect() {
  const { id } = useParams();
  return <Navigate to={`/profile/people/${id}`} replace />;
}

export default function App() {
  return (
    <div className="min-h-screen flex bg-surface-50">
      <Sidebar />
      <div className="flex-1 min-w-0 flex flex-col">
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/calendar" element={<CalendarPage />} />
          <Route
            path="*"
            element={
              <main className="max-w-4xl mx-auto px-4 py-6 w-full">
                <Routes>
                  <Route
                    path="/profile"
                    element={<Navigate to="/profile/personal" replace />}
                  />
                  <Route path="/profile/personal" element={<ProfilePage />} />
                  <Route path="/profile/people" element={<PeoplePage />} />
                  <Route
                    path="/profile/people/new"
                    element={<PersonDetailForm />}
                  />
                  <Route
                    path="/profile/people/:id"
                    element={<PersonDetailForm />}
                  />
                  <Route
                    path="/people"
                    element={<Navigate to="/profile/people" replace />}
                  />
                  <Route
                    path="/people/new"
                    element={<Navigate to="/profile/people/new" replace />}
                  />
                  <Route path="/people/:id" element={<PersonIdRedirect />} />
                  <Route path="/todos" element={<TodosPage />} />
                  <Route path="/planning" element={<PlanningPage />} />
                </Routes>
              </main>
            }
          />
        </Routes>
      </div>
    </div>
  );
}
