import { Routes, Route } from "react-router-dom";
import NavBar from "./components/layout/NavBar";
import ChatPage from "./components/chat/ChatPage";
import ProfilePage from "./components/profile/ProfilePage";
import PeoplePage from "./components/people/PeoplePage";
import PersonDetailForm from "./components/people/PersonDetailForm";
import TodosPage from "./components/todos/TodosPage";
import PlanningPage from "./components/planning/PlanningPage";
import CalendarPage from "./components/calendar/CalendarPage";

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <NavBar />
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="/calendar" element={<CalendarPage />} />
        <Route
          path="*"
          element={
            <main className="max-w-4xl mx-auto px-4 py-6 w-full">
              <Routes>
                <Route path="/profile" element={<ProfilePage />} />
                <Route path="/people" element={<PeoplePage />} />
                <Route path="/people/new" element={<PersonDetailForm />} />
                <Route path="/people/:id" element={<PersonDetailForm />} />
                <Route path="/todos" element={<TodosPage />} />
                <Route path="/planning" element={<PlanningPage />} />
              </Routes>
            </main>
          }
        />
      </Routes>
    </div>
  );
}
