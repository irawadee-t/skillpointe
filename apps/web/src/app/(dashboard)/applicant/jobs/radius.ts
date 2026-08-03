/**
 * Radius presets for the browse-jobs distance filter — shared by the server
 * page (URL validation) and the client control (pills). Lives in its own
 * module so the client bundle never imports the server page (which pulls in
 * next/headers via the Supabase server client).
 */
export const RADIUS_PRESETS = [10, 25, 50, 100, 250] as const;
