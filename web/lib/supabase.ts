import { createClient, SupabaseClient } from "@supabase/supabase-js";

let client: SupabaseClient | null = null;
export const supabase = () => (client ??= createClient(process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://localhost", process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "anon"));
