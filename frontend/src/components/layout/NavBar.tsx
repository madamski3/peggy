import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "Chat" },
  { to: "/profile", label: "Profile" },
  { to: "/people", label: "People" },
  { to: "/todos", label: "Todos" },
  { to: "/planning", label: "Planning" },
  { to: "/calendar", label: "Calendar" },
];

export default function NavBar() {
  return (
    <nav className="bg-white border-b border-gray-200">
      <div className="max-w-4xl mx-auto px-4 flex items-center h-14 gap-8">
        <span className="font-semibold text-lg text-gray-800">Assistant</span>
        <div className="flex gap-6">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.to === "/"}
              className={({ isActive }) =>
                `text-sm font-medium transition-colors ${
                  isActive
                    ? "text-blue-600 border-b-2 border-blue-600 pb-0.5"
                    : "text-gray-500 hover:text-gray-800"
                }`
              }
            >
              {link.label}
            </NavLink>
          ))}
        </div>
      </div>
    </nav>
  );
}
