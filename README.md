# HA Gecko Kiosk

Public **Home Assistant custom integration** for an Android GeckoView kiosk controlled via MQTT. **Experimental**: validate on your own Home Assistant setup before relying on it.

**Integration version:** `0.2.0` · **Domain:** `ha_gecko_kiosk`.

## Installeren in Home Assistant (HACS / Marketplace)

1. Open in HACS **Custom repositories**, of in nieuwere Home Assistant-versies **Settings → Marketplace → Custom repositories**.
2. Voeg `https://github.com/Alec-99/Alec-99-ha-gecko-kiosk` toe als **Integration**.
3. Installeer **HA Gecko Kiosk** vanuit de standaardbranch en herstart Home Assistant.
4. Kies **Instellingen → Apparaten en diensten → Integratie toevoegen → HA Gecko Kiosk**.
5. Open het beheerpaneel **Gecko-kiosken** met een administratoraccount.

Zorg dat de Home Assistant **MQTT-integratie** al werkt en dat je Android Gecko Kiosk-app dezelfde broker gebruikt.

Handmatig installeren: kopieer de map `custom_components/ha_gecko_kiosk` naar `/config/custom_components/ha_gecko_kiosk`, herstart HA en voeg de integratie toe.

## Functies / Features

- MQTT tabletstatus en beschikbaarheid; beheren via een HA-sidebarpaneel
- Native cameracommandos: `prewarm`, `show`, `hide`, `stop`
- Bevestigingsvensters, berichten en cameravensters met antwoordevents
- Schermbeveiligingsmeldingen en UI-instellingen
- Tabletbediening waaronder helderheid, volume en dashboard herladen

Beschikbare HA-acties: `ha_gecko_kiosk.camera`, `ha_gecko_kiosk.device`, `ha_gecko_kiosk.popup`, `ha_gecko_kiosk.notification`, `ha_gecko_kiosk.set_screensaver`, `ha_gecko_kiosk.set_camera_popup`, `ha_gecko_kiosk.get_settings`, `ha_gecko_kiosk.reset_settings`.

Apparaattopics gebruiken het patroon `ha_kiosk/<device_id>/`. Wachtwoorden, lokale dashboard-URL's en camerastreamadressen staan **niet** in deze repository.

## Scope en teststatus

Deze repository bevat **uitsluitend de publieke HA-integratie**, geen Android APK, persoonlijke deviceconfiguratie, hardwarelogs of oude private Git-geschiedenis. Android-app en OTA-installer blijven voorlopig buiten deze publicatie.

Deze broncode is overgenomen uit een geselecteerde private experimentele ontwikkelbranch, met aparte publieke versiegeschiedenis. De CI test basiscontracten en syntaxis; dat bewijst **geen** werkende fysieke tablet of productie-installatie. Verwijder Browser Mod of oudere kiosk-integraties pas nadat alle bestaande functies zijn gecontroleerd.

Zie [publicatiebeleid](docs/PUBLISHING.md). Nog geen projectlicentie gekozen: publiek zichtbaar betekent **niet automatisch opensource gelicentieerd**.
