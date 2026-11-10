import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../config/roles";
import ClockWidget from "./ClockWidget";

const POSITION_KEY = "hrms_quick_attendance_position";
const EDGE_PADDING = 8;

export default function FloatingAttendanceWidget() {
  const { pathname } = useLocation();
  const { user, hasClockInOut } = useAuth();
  const widgetRef = useRef(null);
  const dragRef = useRef(null);
  const positionRef = useRef(null);
  const suppressClickRef = useRef(false);
  const [position, setPosition] = useState(null);
  const [minimized, setMinimized] = useState(false);
  const [dragging, setDragging] = useState(false);

  const shouldShow = user
    && hasClockInOut
    && [ROLES.EMPLOYEE, ROLES.MANAGER].includes(user.role)
    && pathname !== "/"
    && pathname !== "/login"
    && !pathname.startsWith("/test/");

  const clampPosition = (next) => {
    const rect = widgetRef.current?.getBoundingClientRect();
    const width = rect?.width || (minimized ? 58 : 292);
    const height = rect?.height || (minimized ? 58 : 180);
    return {
      x: Math.max(EDGE_PADDING, Math.min(next.x, window.innerWidth - width - EDGE_PADDING)),
      y: Math.max(EDGE_PADDING, Math.min(next.y, window.innerHeight - height - EDGE_PADDING)),
    };
  };

  const updatePosition = (next) => {
    const safePosition = clampPosition(next);
    positionRef.current = safePosition;
    setPosition(safePosition);
  };

  useEffect(() => {
    let savedPosition = null;
    try {
      savedPosition = JSON.parse(localStorage.getItem(POSITION_KEY));
    } catch (error) {
      console.warn("Could not restore the Quick Attendance position.", error);
    }

    const initialPosition = savedPosition
      && Number.isFinite(savedPosition.x)
      && Number.isFinite(savedPosition.y)
      ? savedPosition
      : { x: window.innerWidth - 316, y: window.innerHeight - 204 };
    const safePosition = clampPosition(initialPosition);
    positionRef.current = safePosition;
    setPosition(safePosition);
  }, []);

  useLayoutEffect(() => {
    if (!position) return;
    const safePosition = clampPosition(position);
    if (safePosition.x !== position.x || safePosition.y !== position.y) {
      positionRef.current = safePosition;
      setPosition(safePosition);
    }
  }, [minimized, position]);

  useEffect(() => {
    if (!position) return;
    try {
      localStorage.setItem(POSITION_KEY, JSON.stringify(position));
    } catch (error) {
      console.warn("Could not save the Quick Attendance position.", error);
    }
  }, [position]);

  useEffect(() => {
    const handleResize = () => {
      if (positionRef.current) updatePosition(positionRef.current);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [minimized]);

  const handlePointerDown = (event) => {
    if (event.button !== 0 && event.pointerType !== "touch") return;
    if (!minimized && event.target.closest("[data-no-drag]")) return;
    if (!positionRef.current) return;
    suppressClickRef.current = false;
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      offsetX: event.clientX - positionRef.current.x,
      offsetY: event.clientY - positionRef.current.y,
      moved: false,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
  };

  const handlePointerMove = (event) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (!drag.moved && Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) > 4) {
      drag.moved = true;
      suppressClickRef.current = true;
    }
    if (drag.moved) {
      updatePosition({ x: event.clientX - drag.offsetX, y: event.clientY - drag.offsetY });
    }
  };

  const handlePointerUp = (event) => {
    if (dragRef.current?.pointerId !== event.pointerId) return;
    dragRef.current = null;
    setDragging(false);
  };

  const handleMinimizedClick = (event) => {
    if (suppressClickRef.current) {
      event.preventDefault();
      suppressClickRef.current = false;
      return;
    }
    setMinimized(false);
  };

  if (!shouldShow || !position) return null;

  const dragHandlers = {
    onPointerDown: handlePointerDown,
    onPointerMove: handlePointerMove,
    onPointerUp: handlePointerUp,
    onPointerCancel: handlePointerUp,
  };

  return (
    <div
      ref={widgetRef}
      className={`quick-attendance-positioner${minimized ? " is-minimized" : ""}${dragging ? " is-dragging" : ""}`}
      style={{ left: position.x, top: position.y }}
    >
      <ClockWidget
        presentation="floating"
        minimized={minimized}
        onToggleMinimized={() => setMinimized((current) => !current)}
        onMinimizedClick={handleMinimizedClick}
        dragHandlers={dragHandlers}
      />
    </div>
  );
}
