import { NextRequest } from "next/server";
import { staffApi } from "@/lib/staff/server-api";

const path = async (params: Promise<{ id: string }>) => `/staff/profiles/${(await params).id}/competencies/`;
export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) { return staffApi(request, await path(params)); }
export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) { return staffApi(request, await path(params), { method: "POST", body: await request.text() }); }
export async function DELETE(request: NextRequest, { params }: { params: Promise<{ id: string }> }) { return staffApi(request, await path(params), { method: "DELETE", body: await request.text() }); }
