import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  Calendar,
  CheckSquare,
  ChevronDown,
  ChevronRight,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Sparkles,
  User,
  UserRound,
  Users,
  type LucideIcon,
} from "lucide-react";

type NavChild = {
  to: string;
  label: string;
  icon: LucideIcon;
};

type NavItem = {
  label: string;
  icon: LucideIcon;
  to?: string;
  end?: boolean;
  match?: string;
  children?: NavChild[];
};

const navItems: NavItem[] = [
  { to: "/", label: "Chat", icon: MessageSquare, end: true },
  { to: "/calendar", label: "Calendar", icon: Calendar },
  { to: "/todos", label: "Todos", icon: CheckSquare },
  { to: "/planning", label: "Planning", icon: Sparkles },
  {
    label: "Profile",
    icon: User,
    match: "/profile",
    children: [
      { to: "/profile/personal", label: "Personal", icon: UserRound },
      { to: "/profile/people", label: "People", icon: Users },
    ],
  },
];

const COLLAPSED_STORAGE_KEY = "sidebar:collapsed";

function readCollapsed(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(COLLAPSED_STORAGE_KEY) === "1";
}

export default function Sidebar() {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState<boolean>(readCollapsed);
  const [profileOpen, setProfileOpen] = useState<boolean>(() =>
    location.pathname.startsWith("/profile"),
  );

  useEffect(() => {
    window.localStorage.setItem(COLLAPSED_STORAGE_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  useEffect(() => {
    if (location.pathname.startsWith("/profile")) {
      setProfileOpen(true);
    }
  }, [location.pathname]);

  return (
    <aside
      className={`shrink-0 border-r border-surface-200 bg-white h-screen sticky top-0 flex flex-col transition-[width] duration-200 ease-out ${
        collapsed ? "w-16" : "w-60"
      }`}
    >
      <div
        className={`flex items-center h-14 border-b border-surface-200 ${
          collapsed ? "justify-center px-0" : "justify-between px-4"
        }`}
      >
        {!collapsed && (
          <span className="font-semibold text-gray-800 tracking-tight">
            Assistant
          </span>
        )}
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          className="p-1.5 rounded-md text-gray-500 hover:text-primary-700 hover:bg-primary-50 transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500/40"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <PanelLeftOpen className="h-5 w-5" />
          ) : (
            <PanelLeftClose className="h-5 w-5" />
          )}
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto py-3">
        <ul className="flex flex-col gap-0.5 px-2">
          {navItems.map((item) =>
            item.children ? (
              <GroupItem
                key={item.label}
                item={item}
                collapsed={collapsed}
                open={profileOpen}
                onToggle={() => setProfileOpen((o) => !o)}
              />
            ) : (
              <LeafItem key={item.to} item={item} collapsed={collapsed} />
            ),
          )}
        </ul>
      </nav>
    </aside>
  );
}

function LeafItem({
  item,
  collapsed,
  nested = false,
}: {
  item: NavItem | NavChild;
  collapsed: boolean;
  nested?: boolean;
}) {
  const Icon = item.icon;
  const to = "to" in item && item.to ? item.to : "/";
  const end = "end" in item ? item.end : undefined;
  return (
    <li>
      <NavLink
        to={to}
        end={end}
        title={collapsed ? item.label : undefined}
        className={({ isActive }) =>
          [
            "group flex items-center gap-3 rounded-lg text-sm font-medium transition-colors",
            collapsed ? "justify-center h-10 w-10 mx-auto" : "px-3 py-2",
            nested && !collapsed ? "pl-9" : "",
            isActive
              ? "bg-primary-50 text-primary-700"
              : "text-gray-600 hover:text-gray-900 hover:bg-surface-100",
          ]
            .filter(Boolean)
            .join(" ")
        }
      >
        <Icon className="h-[18px] w-[18px] shrink-0" />
        {!collapsed && <span className="truncate">{item.label}</span>}
      </NavLink>
    </li>
  );
}

function GroupItem({
  item,
  collapsed,
  open,
  onToggle,
}: {
  item: NavItem;
  collapsed: boolean;
  open: boolean;
  onToggle: () => void;
}) {
  const location = useLocation();
  const Icon = item.icon;
  const isActiveBranch = item.match
    ? location.pathname.startsWith(item.match)
    : false;

  if (collapsed) {
    return (
      <>
        <li>
          <div
            title={item.label}
            className={`flex items-center justify-center h-10 w-10 mx-auto rounded-lg text-sm font-medium ${
              isActiveBranch
                ? "bg-primary-50 text-primary-700"
                : "text-gray-600"
            }`}
          >
            <Icon className="h-[18px] w-[18px]" />
          </div>
        </li>
        {item.children?.map((child) => (
          <LeafItem key={child.to} item={child} collapsed />
        ))}
      </>
    );
  }

  return (
    <>
      <li>
        <button
          type="button"
          onClick={onToggle}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
            isActiveBranch
              ? "text-primary-700"
              : "text-gray-600 hover:text-gray-900 hover:bg-surface-100"
          }`}
          aria-expanded={open}
        >
          <Icon className="h-[18px] w-[18px] shrink-0" />
          <span className="flex-1 text-left truncate">{item.label}</span>
          {open ? (
            <ChevronDown className="h-4 w-4 text-gray-400" />
          ) : (
            <ChevronRight className="h-4 w-4 text-gray-400" />
          )}
        </button>
      </li>
      {open &&
        item.children?.map((child) => (
          <LeafItem key={child.to} item={child} collapsed={false} nested />
        ))}
    </>
  );
}
