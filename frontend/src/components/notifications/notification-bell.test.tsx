import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NotificationBell } from "./notification-bell";

const navigation = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => navigation }));

const summary = { unread_count: 1, category_counts: { APPOINTMENTS: 1 } };
const notification = {
  id: "notification-1",
  notification_type: "APPOINTMENT_CONFIRMED",
  category: "APPOINTMENTS",
  title: "Appointment confirmed",
  message: "Your physiotherapy appointment is confirmed.",
  target_url: "/customer/appointments/appointment-1",
  action_required: false,
  is_read: false,
  read_at: null,
  created_at: "2026-09-15T10:00:00Z",
};

function response(value: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => {
  vi.restoreAllMocks();
  navigation.push.mockReset();
  navigation.refresh.mockReset();
  vi.useRealTimers();
});

describe("NotificationBell", () => {
  it.each(["OWNER", "CUSTOMER", "PHYSIOTHERAPIST"] as const)("shows an accessible unread bell for %s", async (role) => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response(summary));
    render(<NotificationBell role={role} onSummary={vi.fn()} />);
    expect(await screen.findByRole("button", { name: /Notifications, 1 unread/i })).toBeInTheDocument();
  });

  it("opens without clearing unread, distinguishes state, then marks only the selected item and follows its deep link", async () => {
    const backend = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/read?")) return response({ ...notification, is_read: true, read_at: "2026-09-15T10:01:00Z" });
      if (url.startsWith("/api/notifications?")) return response({ ...summary, count: 1, next: null, previous: null, results: [notification] });
      return response(summary);
    });
    const onSummary = vi.fn();
    render(<NotificationBell role="CUSTOMER" onSummary={onSummary} />);
    const bell = await screen.findByRole("button", { name: /Notifications, 1 unread/i });
    await userEvent.click(bell);

    expect(await screen.findByRole("dialog", { name: "Notifications" })).toBeInTheDocument();
    expect(screen.queryByText(/Unread ·/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Notification event time")).toHaveAttribute("datetime", notification.created_at);
    expect(backend.mock.calls.some(([input]) => String(input).includes("/read?"))).toBe(false);

    await userEvent.click(screen.getByRole("button", { name: /Appointment confirmed/ }));
    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/customer/appointments/appointment-1"));
    expect(onSummary).toHaveBeenLastCalledWith(expect.objectContaining({ unread_count: 0 }));
    expect(backend.mock.calls.filter(([input, init]) => String(input).includes("/read?") && init?.method === "POST")).toHaveLength(1);
  });

  it("renders empty and recoverable error states", async () => {
    let failList = false;
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      if (String(input).startsWith("/api/notifications?") && failList) return response({ detail: "failed" }, 503);
      if (String(input).startsWith("/api/notifications?")) return response({ ...summary, unread_count: 0, count: 0, next: null, previous: null, results: [] });
      return response({ unread_count: 0, category_counts: {} });
    });
    const { unmount } = render(<NotificationBell role="OWNER" onSummary={vi.fn()} />);
    await userEvent.click(await screen.findByRole("button", { name: /Notifications, 0 unread/i }));
    expect(await screen.findByText("You’re all caught up.")).toBeInTheDocument();
    unmount();

    failList = true;
    render(<NotificationBell role="OWNER" onSummary={vi.fn()} />);
    await userEvent.click(await screen.findByRole("button", { name: /Notifications, 0 unread/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Notifications could not be loaded");
    expect(screen.getByRole("button", { name: "Retry" })).toHaveClass("min-h-11");
  });

  it("refreshes the lightweight unread count on polling and window focus", async () => {
    vi.useFakeTimers();
    const backend = vi.spyOn(globalThis, "fetch").mockImplementation(() => response(summary));
    render(<NotificationBell role="PHYSIOTHERAPIST" onSummary={vi.fn()} />);
    await act(async () => { vi.advanceTimersByTime(0); await Promise.resolve(); });
    const initial = backend.mock.calls.length;
    await act(async () => { vi.advanceTimersByTime(45_000); await Promise.resolve(); });
    expect(backend.mock.calls.length).toBeGreaterThan(initial);
    const afterPoll = backend.mock.calls.length;
    act(() => window.dispatchEvent(new Event("focus")));
    await act(async () => { await Promise.resolve(); });
    expect(backend.mock.calls.length).toBeGreaterThan(afterPoll);
  });
});
