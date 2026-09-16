export type NotificationCategory = "APPOINTMENTS" | "PRACTITIONERS" | "PAYMENTS" | "REVIEWS";

export type NotificationItem = {
  id: string;
  notification_type: string;
  category: NotificationCategory;
  title: string;
  message: string;
  target_url: string;
  action_required: boolean;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
};

export type NotificationSummary = {
  unread_count: number;
  category_counts: Partial<Record<NotificationCategory, number>>;
};

export type NotificationPage = NotificationSummary & {
  count: number;
  next: string | null;
  previous: string | null;
  results: NotificationItem[];
};
