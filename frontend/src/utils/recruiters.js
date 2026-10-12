import client from "../api/client";

// Recruiters (id + name) for filter dropdowns. Only Finance / HR Operations /
// Managers may call the overview endpoint — for everyone else this quietly
// returns [] so the caller can simply hide the filter.
export async function fetchRecruiterOptions() {
  try {
    const { data } = await client.get("/recruitment/recruiters");
    return (data.recruiters || []).map((r) => ({ id: r.id, name: r.full_name, active: r.is_active }));
  } catch {
    return [];
  }
}
