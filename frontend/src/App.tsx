import { Routes, Route } from "react-router-dom";
import NavBar from "./components/layout/NavBar";
import ChatPage from "./components/chat/ChatPage";
import ProfilePage from "./components/profile/ProfilePage";
import PeoplePage from "./components/people/PeoplePage";
import PersonDetailForm from "./components/people/PersonDetailForm";
import TodosPage from "./components/todos/TodosPage";
import TasksPage from "./components/tasks/TasksPage";

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <NavBar />
      <Routes>
        <Route path="/" element={<ChatPage />} />
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
                <Route path="/tasks" element={<TasksPage />} />
              </Routes>
            </main>
          }
        />
      </Routes>
    </div>
  );
}
