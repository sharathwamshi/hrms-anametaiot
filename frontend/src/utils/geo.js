/**
 * Asks the browser for the person's current position. Resolves with
 * { latitude, longitude, accuracy } or { error } — never rejects, because attendance
 * uses SOFT geofencing: a missing location must never stop someone from clocking in.
 */
export function getBrowserLocation(timeoutMs = 9000) {
  return new Promise((resolve) => {
    if (!("geolocation" in navigator)) {
      resolve({ error: "This browser can't share a location." });
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ latitude: pos.coords.latitude, longitude: pos.coords.longitude, accuracy: pos.coords.accuracy }),
      (err) => resolve({
        error: err.code === 1
          ? "Location is blocked for this site — allow it in your browser to record where you punched."
          : "Couldn't get your location this time.",
      }),
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 5000 },
    );
  });
}

export const mapsUrl = (lat, lng) => `https://www.google.com/maps?q=${lat},${lng}`;
