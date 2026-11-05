// Optional Gecko-kiosk climate preloader (experimental).
// Keep feature lightweight: preload the HA control module without creating a second Gecko session.
const MAX_TRIES = 5;
const RETRY_MS = 1000;
async function preloadClimate(tries = 0) {
  try {
    if (typeof window.loadCardHelpers !== "function") {
      if (tries < MAX_TRIES) window.setTimeout(() => preloadClimate(tries + 1), RETRY_MS);
      return;
    }
    const helpers = await window.loadCardHelpers();
    if (typeof helpers?.importMoreInfoControl === "function") {
      await helpers.importMoreInfoControl("climate");
      console.info("[HA Gecko Kiosk] Thermostaatmodule vooraf geladen.");
    } else {
      console.info("[HA Gecko Kiosk] Meer-info preloading niet ondersteund door deze HA-versie.");
    }
  } catch (error) {
    console.warn("[HA Gecko Kiosk] Voorladen thermostaat niet gelukt; standaard bediening blijft beschikbaar.", error);
  }
}
window.setTimeout(() => preloadClimate(), 1800);
