import { NextRequest, NextResponse } from "next/server";

/** Admin lives on its own host (NEXT_PUBLIC_ADMIN_HOST). On any other host /admin does not exist. */
export function middleware(req: NextRequest) {
  const host = req.headers.get("host") ?? "";
  const adminHost = process.env.NEXT_PUBLIC_ADMIN_HOST;
  const p = req.nextUrl.pathname;
  const onAdmin = !!adminHost && host === adminHost;
  if (onAdmin && !p.startsWith("/admin") && !/^\/(verify|p)\//.test(p)) {
    const u = req.nextUrl.clone();
    u.pathname = "/admin" + (p === "/" ? "" : p);
    return NextResponse.rewrite(u);
  }
  const devOpen = process.env.NODE_ENV !== "production" && !adminHost;
  if (!onAdmin && p.startsWith("/admin") && !devOpen) return new NextResponse("Not found", { status: 404 });
  return NextResponse.next();
}
export const config = { matcher: ["/((?!_next|favicon.ico).*)"] };
