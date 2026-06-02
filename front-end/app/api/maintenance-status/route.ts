import { NextResponse } from "next/server"

import { API_URL } from "@/lib/config"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

export async function GET() {
  try {
    const response = await fetch(`${API_URL}/v1/maintenance/status`, {
      cache: "no-store",
    })
    if (!response.ok) {
      return NextResponse.json(
        { status: "none", message: "", eta: "" },
        { status: 200 },
      )
    }
    const payload = await response.json()
    return NextResponse.json(payload, { status: 200 })
  } catch {
    return NextResponse.json(
      { status: "none", message: "", eta: "" },
      { status: 200 },
    )
  }
}
