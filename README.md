# HA Gecko Kiosk

![HA Gecko Kiosk — graphite and orange identity](assets/brand/github-readme-banner-1600x400.png)

Public **Home Assistant custom integration** for an Android GeckoView kiosk controlled via MQTT. **Experimental**: validate on your own Home Assistant setup before relying on it.

**Integration version:** `0.5.0` · **Domain:** `ha_gecko_kiosk`.

## Installeren in Home Assistant (HACS / Marketplace)

1. Open in HACS **Custom repositories**, of in nieuwere Home Assistant-versies **Settings → Marketplace → Custom repositories**.
2. Voeg `https://github.com/Alec-99/Alec-99-ha-gecko-kiosk` toe als **Integration**.
3. Installeer **HA Gecko Kiosk** vanuit de standaardbranch en herstart Home Assistant.
4. Kies **Instellingen → Apparaten en diensten → Integratie toevoegen → HA Gecko Kiosk**.
5. Open het beheerpaneel **Gecko-kiosken** met een administratoraccount.

Zorg dat de Home Assistant **MQTT-integratie** al werkt en dat je Android Gecko Kiosk-app dezelfde broker gebruikt.

Handmatig installeren: kopieer de map `custom_components/ha_gecko_kiosk` naar `/config/custom_components/ha_gecko_kiosk`, herstart HA en voeg de integratie toe.

## Functies / Features

- Aangesloten kiosken als HA-apparaten, met native sensoren en bediening op basis van ondersteunde mogelijkheden
- MQTT tabletstatus en beschikbaarheid; beheren via een HA-sidebarpaneel
- Native cameracommandos: `prewarm`, `show`, `hide`, `stop`
- Bevestigingsvensters, berichten en cameravensters met antwoordevents
- Schermbeveiligingsmeldingen en UI-instellingen
- Tabletbediening waaronder helderheid, volume en dashboard herladen
- APK uploaden vanuit de browser en op een gekozen kiosk installeren; voortgang ook via een HA-update-entiteit

Beschikbare HA-acties: `ha_gecko_kiosk.camera`, `ha_gecko_kiosk.device`, `ha_gecko_kiosk.popup`, `ha_gecko_kiosk.notification`, `ha_gecko_kiosk.set_screensaver`, `ha_gecko_kiosk.set_camera_popup`, `ha_gecko_kiosk.get_settings`, `ha_gecko_kiosk.reset_settings`.

Apparaattopics gebruiken het patroon `ha_kiosk/<device_id>/`. Wachtwoorden, lokale dashboard-URL's en camerastreamadressen staan **niet** in deze repository.

De generieke capability-advertentie voor Gecko- en toekomstige kioskclients is beschreven in [MQTT capability manifest, version 1](docs/MQTT_CAPABILITIES.md).

De sidebar, documentatie en integratie-iconen gebruiken de graphite/orange-identiteit; de volledige projectbrede bronset staat niet in deze publieke integratierepository.

## Apparaten en entiteiten

Vanaf 0.3.0 verschijnen kiosken bij **Instellingen → Apparaten en diensten → HA Gecko Kiosk** zodra hun status binnenkomt. Ondersteunde entiteiten: verbinding, kiosk actief, batterij/laden/temperatuur/spanning, appversie, watchdog, MQTT-herverbindingen, scherm, schermhelderheid, schermbeveiliging, volume, dempen, dashboard vernieuwen en het laatste opdrachtresultaat. Entiteiten ontstaan alleen bij bewijs van ondersteuning; offline bediening is geblokkeerd.

Bestaande MQTT-discovery-entiteiten behouden hun ID en geschiedenis; de integratie voegt daarvoor geen tweede native equivalent toe. HA-versies met één apparaat per config-entry tonen het MQTT-apparaat en het integratieapparaat als gekoppelde apparaten via dezelfde bewezen identiteit. Op oudere HA-versies wordt het fysieke apparaat gedeeld. Naam, model en fabrikant worden alleen uit de kioskdiscovery overgenomen. YAML-installaties krijgen automatisch dezelfde config-entry.

Na bijwerken **HA herstarten**. MQTT moet aangesloten zijn en de kiosk moet opnieuw verbinden om zijn discovery en status te melden. Geen apparaten zichtbaar: controleer eerst of `ha_kiosk/<id>/availability` en de overige statusberichten dezelfde broker bereiken.

## APK-updates vanuit HA

Installeer eerst één keer handmatig een OTA-geschikte app (Gecko 0.8.6 of nieuwer) met dezelfde signing key. Oudere apps kunnen zichzelf nog niet via MQTT bijwerken.

1. Open **Gecko-kiosken → App-updates**.
2. Kies je `.apk`-bestand en klik **APK uploaden**. HA leest versie en buildnummer automatisch uit het bestand.
3. Selecteer de kiosk en klik **Installeren op …**. De voortgang verschijnt in hetzelfde scherm.

Je hebt hiervoor geen GitHub-token, repository-instellingen of apart manifestbestand nodig. De geüploade APK blijft beschikbaar na een HA-herstart en verschijnt ook in de **App-update**-entiteit. Oudere of gelijke buildnummers worden geweigerd; de tablet controleert de hash, pakketnaam en ondertekening. Android kan om lokale installatiebevestiging vragen.

De eerder toegevoegde GitHub CI-bron blijft optioneel beschikbaar via de integratieopties. Een browserupload krijgt voorrang op die bron.

Zie [OTA-protocol, configuratie en beperkingen](docs/OTA.md).

## Scope en teststatus

Deze repository bevat **uitsluitend de publieke HA-integratie**, geen Android APK, persoonlijke deviceconfiguratie, hardwarelogs of oude private Git-geschiedenis. Android-app en OTA-installer blijven voorlopig buiten deze publicatie.

Deze broncode is overgenomen uit een geselecteerde private experimentele ontwikkelbranch, met aparte publieke versiegeschiedenis. De CI test basiscontracten en syntaxis; dat bewijst **geen** werkende fysieke tablet of productie-installatie. Verwijder Browser Mod of oudere kiosk-integraties pas nadat alle bestaande functies zijn gecontroleerd.

Zie [publicatiebeleid](docs/PUBLISHING.md). Nog geen projectlicentie gekozen: publiek zichtbaar betekent **niet automatisch opensource gelicentieerd**.

## Codex-overdracht

Voor het verdere UI-herontwerp, de iconen en de bewuste scheiding tussen de private ontwikkelrepo en deze publieke HACS-testrepo: [Codex-handoff UI & branding](docs/HANDOFF_CODEX_UI_BRANDING_2026-11-06.md).
