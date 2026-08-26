import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  const enabled = process.env.MSG91_ENABLED?.toLowerCase() === "true";
  if (!enabled) return NextResponse.json({ enabled: false });
  const widgetId = process.env.MSG91_WIDGET_ID;
  const tokenAuth = process.env.MSG91_WIDGET_TOKEN;
  if (!widgetId || !tokenAuth) {
    return NextResponse.json({ detail: "Mobile verification is not configured." }, { status: 503 });
  }
  return NextResponse.json({ enabled: true, widgetId, tokenAuth });
}
