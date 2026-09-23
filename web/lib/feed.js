// Shared loader for the three boards: live feed first, bundled sample as a labelled fallback.
export async function loadBoard({ liveUrl, sampleUrl, scenario, sources }) {
  if (scenario && scenario !== "Live feed" && sources[scenario]) {
    const data = await fetch(sources[scenario]).then((r) => r.json());
    return { data, feed: "sample", feedNotice: null };
  }
  try {
    const r = await fetch(liveUrl, { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return { data: await r.json(), feed: "live", feedNotice: null };
  } catch (err) {
    const data = await fetch(sampleUrl).then((r) => r.json());
    return { data, feed: "sample", feedNotice: `The live feed is not reachable (${err.message}). Showing a sample board so the layout can be reviewed; nothing on it is a current projection.` };
  }
}
