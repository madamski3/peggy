import { useEffect } from "react";
import type { CalendarEvent } from "../../types/calendar";

interface Props {
  event: CalendarEvent;
  anchor: { x: number; y: number } | null;
  onClose: () => void;
}

function formatRange(event: CalendarEvent): string {
  if (!event.start) return "";
  const start = new Date(event.start);
  const end = event.end ? new Date(event.end) : null;
  if (event.allDay) {
    return start.toLocaleDateString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
    });
  }
  const dateFmt: Intl.DateTimeFormatOptions = {
    weekday: "short",
    month: "short",
    day: "numeric",
  };
  const timeFmt: Intl.DateTimeFormatOptions = {
    hour: "numeric",
    minute: "2-digit",
  };
  const datePart = start.toLocaleDateString(undefined, dateFmt);
  const startTime = start.toLocaleTimeString(undefined, timeFmt);
  if (!end) return `${datePart} · ${startTime}`;
  const endTime = end.toLocaleTimeString(undefined, timeFmt);
  return `${datePart} · ${startTime} – ${endTime}`;
}

export default function EventDetails({ event, anchor, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const desktopStyle: React.CSSProperties | undefined = anchor
    ? {
        top: Math.min(anchor.y + 8, window.innerHeight - 320),
        left: Math.min(anchor.x, window.innerWidth - 360),
      }
    : undefined;

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/30 sm:bg-transparent"
        onClick={onClose}
      />
      <div
        className="fixed z-50 bg-white shadow-xl border border-gray-200
                   inset-x-0 bottom-0 rounded-t-2xl p-4 max-h-[75vh] overflow-y-auto
                   sm:inset-auto sm:bottom-auto sm:rounded-lg sm:w-[340px] sm:max-h-[400px]"
        style={desktopStyle}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 mb-2">
          <h3 className="font-semibold text-gray-900 leading-snug">
            {event.title}
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none"
            aria-label="Close"
          >
            ×
          </button>
        </div>
        <div className="text-sm text-gray-700 space-y-2">
          <div>{formatRange(event)}</div>
          {event.extendedProps.location && (
            <div className="text-gray-600">
              <span className="font-medium">Where:</span>{" "}
              {event.extendedProps.location}
            </div>
          )}
          {event.extendedProps.description && (
            <div className="text-gray-600 whitespace-pre-wrap break-words">
              {event.extendedProps.description}
            </div>
          )}
          {event.extendedProps.isAssistantCreated && (
            <div className="text-xs text-primary-700 bg-primary-50 px-2 py-1 rounded inline-block">
              Created by assistant
            </div>
          )}
        </div>
      </div>
    </>
  );
}
