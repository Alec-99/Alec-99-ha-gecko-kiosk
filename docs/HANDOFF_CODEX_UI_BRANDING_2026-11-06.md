# Codex-handoff — HA Gecko Kiosk: UI, iconen en publieke distributie

**Opgesteld en geverifieerd:** 6 november 2026  
**Doel:** een volgende Codex-agent kan het huidige werk zelfstandig, veilig en controleerbaar verderzetten.  
**Belangrijkste status:** de publieke HA-integratie bestaat en bouwt; **de UI-redesign is nog NIET uitgevoerd**. Dit document is een overdracht, geen bewijs dat de volgende taken al af zijn.

## 1. Waarom we bewust TWEE repositories hebben

Dit is een harde architectuur- en privacybeslissing, niet zomaar een tijdelijke workaround.

### Repository A — PRIVATE ontwikkelrepository

- Naam: **sm-t580-ha-panel** (privé, niet als publieke bron spiegelen).
- Bevat het volledige project: native Android-app, experimentele GeckoView/LibVLC-kioskapp, Home Assistant-integratie, MQTT-protocollen, hardwareonderzoek, ROM-/camera-/watchdogdiagnostiek, ontwikkeltests en interne documentatie.
- De actuele Gecko-experimentbron bevindt zich in branch **experiment/gecko-cache-nl**. De HA-integratie staat daar onder **home-assistant/custom_components/ha_gecko_kiosk/**.
- **Dit is de bron van waarheid voor de bredere app-ontwikkeling en de persoonlijke hardwaretests**. Eigen toestelconfiguraties en diagnostische gegevens mogen er blijven staan, zolang de repo privé blijft.
- Een vorige controle heeft daadwerkelijk gevoelige apparaat-/netwerkidentificatie in de private geschiedenis bevestigd. Daarom mag deze repo **niet rechtstreeks publiek** en mag de bestaande geschiedenis niet worden meegekopieerd.
- Branch **development** bevat nog een aparte native Android-paneelvariant en geschiedenis; deze is niet hetzelfde als de publieke HA-integratie. Verwar deze ontwikkelpaden niet.

### Repository B — PUBLIEKE test- en distributierepository

- URL: https://github.com/Alec-99/Alec-99-ha-gecko-kiosk
- Naam: **Alec-99-ha-gecko-kiosk** (de werkelijke, door de eigenaar gekozen GitHub-reponaam).
- Bevat uitsluitend gereviewde, **privacyveilige** Home Assistant-integratiebestanden en hun algemene tests, handleiding, iconen en CI.
- Doel: de integratie gemakkelijk als **custom repository in HACS / Home Assistant Marketplace** kunnen toevoegen, installeren en testen; later eventueel een nette communityrelease.
- Ontstaan als **schone repository met eigen commitgeschiedenis**; dus geen fork, Git mirror, subtree met oude private geschiedenis of volledige monorepo-export.
- **Dit is niet de bron van waarheid voor private apparaatconfiguratie of Android-builds**. De publieke map custom_components/ha_gecko_kiosk/ is een expliciet geselecteerde snapshot, niet een permanent automatisch gekoppelde live kopie.
- De publieke repository bevat bewust **geen** Android-APK, tabletlogbestanden, camerabeelden, credentials of private workflows.
- Publiek zichtbaar betekent nog niet opensource gelicentieerd: **er is nog geen expliciete licentie gekozen**.

### Waarom dit belangrijk is

De eigenaar wil in Home Assistant vlot de integratie testen en later eventueel delen, **zonder** serienummers, wifi-/netwerkgegevens, persoonlijke deellinks, dashboarddetails, interne tests of volledige private Git-geschiedenis te publiceren. Verder moeten onaffe Android-appwijzigingen en hardware-experimenten gescheiden blijven van gecontroleerde HA-integratieversies.

### Voorgeschreven overdracht van A naar B

1. Selecteer een specifieke geteste private source commit.
2. Neem **uitsluitend toegelaten bronbestanden** over en controleer de exacte inhoud op privégegevens.
3. Pas eventuele paden, generieke documentatie en versies aan voor de publieke indeling.
4. Maak een aparte publieke featurebranch/PR met inspecteerbare diff.
5. Draai publicatie-/privacychecks, contracttests en zo mogelijk HA-integratietests; review handmatig.
6. Laat de eigenaar expliciet kiezen wanneer de wijziging naar publieke main gaat. **Geen automatische mirror of ongevraagde private-naar-public push.**
7. Publieke releases en GitHub Tags pas na versie- en installatietest; de app en HA-integratie hebben afzonderlijke versienummers.

**Publicatiebeleid:** docs/PUBLISHING.md. Kopieer niet stiekem extra private bestanden, ook niet om tests te repareren.

## 2. Wat is nu werkelijk aanwezig in de publieke repository?

- **main** bevat een zelfstandige HA custom integration, domein **ha_gecko_kiosk**.
- **Manifestversie 0.2.1** in custom_components/ha_gecko_kiosk/manifest.json.
- **Backend**: custom_components/ha_gecko_kiosk/__init__.py (MQTT-subscripties, services, admin-only websockethandler en sidebarpaneel).
- **Frontend**: custom_components/ha_gecko_kiosk/frontend/ha-gecko-kiosk-panel.js — nog de **oorspronkelijke lange kaartenlayout**.
- Overige files: config_flow.py, services.yaml, vertalingen, frontend/ha-gecko-preload.js, hacs.json, README.md.
- **Iconen zijn al aanwezig**:
  - custom_components/ha_gecko_kiosk/brand/icon.png
  - custom_components/ha_gecko_kiosk/brand/icon@2x.png
  - custom_components/ha_gecko_kiosk/frontend/icon.png
- **Sidebar**: de backend registreert momenteel sidebar_icon = **mdi:tablet**. Dat is een MDI-icoon; de PNG wordt niet automatisch het sidebaricoon.
- Tests: tests/ha_gecko_kiosk/test_protocol.py (gesimuleerde HA-host; niet live HA).
- CI: .github/workflows/validate.yml met Python-syntax, JSON, protocoltests, frontend Node-syntax en publicatiecontrole.
- Publicatiechecker: scripts/check_public_snapshot.py. De PNG-iconen zijn **expliciet geallowlist met pad, dimensies en PNG-header**, zodat een willekeurige privécamera-screenshot niet ineens wordt toegelaten.

### CI en reviewstatus bij overdracht

- De vroegere publieke CI-run na icon-toevoeging faalde **alleen** omdat de publicatiechecker nog geen PNG toestond: https://github.com/Alec-99/Alec-99-ha-gecko-kiosk/actions/runs/42134185234
- Dit is daarna gerepareerd met commit **488db35f24dea01da968feaf82890579d2787d97**.
- **De nieuwe controle slaagde**: https://github.com/Alec-99/Alec-99-ha-gecko-kiosk/actions/runs/42135134159
- Dit bewijst syntaxis, protocolmocktests en toegestane bestanden, **niet** de echte zichtbaarheid van iconen in elke HACS-versie of werkende UI-interactie in een browser.
- In de README stond bij audit nog versie 0.2.0 terwijl manifest 0.2.1 vermeldde. Bij deze handoff wordt README met manifest gesynchroniseerd.

## 3. Waarom de gebruiker de HA-UI wil laten verbeteren

De bestaande UI toont per tablet in **één lange kaart**: identifier, beschikbaarheid, batterijpercentage, camerastatus, laden, batterijtemperatuur, twee screensaver-knoppen, een grote uitklapbare formuliersectie met zowel screensaver- als camerapopupinstellingen en vier camerabedieningsknoppen.

Gevolgen:
- weinig visuele hiërarchie; status, bediening en configuratie door elkaar;
- lange formulieren zonder rustige groepering;
- beperkte mobiele overzichtelijkheid en visueel zeer simpele bediening;
- vrijwel geen iconen naast acties of in de header;
- statusmeldingen over verzonden/afgewezen opdrachten zijn slecht zichtbaar;
- de huidige frontend haalt elke ~2 s de complete kiosklijst op en zet in veel situaties **shadowRoot.innerHTML opnieuw**. Er is een gedeeltelijke uitzondering als settings openstaan, maar formulieren, focus, tabs en onopgeslagen wijzigingen blijven kwetsbaar.

### Gewenste informatiearchitectuur

Maak een rustige, leesbare HA-conforme interface met duidelijke tabletselectie en compacte secties:

1. **Overzicht**: titel met klein merkicoon; per kiosk een compacte kaart met naam, online/offline/onbekend, batterij en hooguit twee relevante statusregels. Geen zee van actieknoppen.
2. **Bediening**: duidelijk gegroepeerde bestaande screensaver- en cameracommandos; eventueel de al aanwezige device-opdrachten, maar geen nieuwe niet-ondersteunde MQTT-aansturing verzinnen.
3. **Instellingen**: gescheiden groepen voor schermbeveiliging, klok/uiterlijk en camerapopup. Gebruik goed gelabelde switches, getallenvelden en kleurkiezers met de huidige min/max-validatie. Per sectie opslaan/herstellen blijft werken.
4. **Status/diagnostiek**: bestaande statusvelden en laatste opdrachtbevestiging overzichtelijk tonen; geen backendtelemetrie verzinnen.
5. **Responsive**: goed leesbaar mobiel, touchscreenvriendelijk; naast muis ook toetsenbord en screenreader ondersteunen.

Styling: HA CSS custom properties en kaartstijl, bruikbaar in licht/donker thema; antraciet en **spaarzaam oranje** als eigen branding. Geen statische zwarte achtergronden in het hele paneel waardoor het lichte HA-thema breekt. Kleine consistente iconen (Material Design Icons of ingebouwde HA-icooncomponenten) voor camera, batterij, instellingen, status en schermbeveiliging.

## 4. Functionele contracten die niet stuk mogen

### HA/WebSocket

- WebSocket-berichttype: **ha_gecko_kiosk/list**.
- Admin-only; resultaat: object met sleutel **kiosks** en een array van tabletstatusobjecten.
- Kioskobject bevat in elk geval id en kan availability, status-object, battery-object, settings-object, last_settings_request, last_settings_request_at_ms en last_settings_response bevatten.
- Settings bevatten twee groepen: **screensaver** en **camera_popup**; ze zijn er pas na ontvangst van de tabletstatus. De UI moet ontbrekende data veilig behandelen.

### Bestaande HA-services

- ha_gecko_kiosk.camera: acties **prewarm, show, hide, stop**, huidige UI kiest camera-ID **doorbell**.
- ha_gecko_kiosk.device: o.a. **screensaver** en dashboard reload (zie services.yaml en __init__.py voor exact schema).
- ha_gecko_kiosk.popup en ha_gecko_kiosk.notification.
- ha_gecko_kiosk.set_screensaver en ha_gecko_kiosk.set_camera_popup.
- ha_gecko_kiosk.get_settings en ha_gecko_kiosk.reset_settings.

### MQTT/ACK

- Bekende topicstructuur begint met **ha_kiosk/<id>/**. Daaronder o.a. availability, status/+, battery/+, settings/state en settings/response.
- Alle remote settingscommando's hebben een request_id; antwoorden worden alleen geaccepteerd voor dezelfde kiosk en een geldig verzoek.
- De huidige _settingsStatusText gebruikt ongeveer **65 seconden** om een onbevestigd verzoek als timeout te tonen.
- **Een geslaagde HA-servicecall betekent dat een bericht is gepubliceerd, NIET dat de tablet de wijziging heeft toegepast.** Toon dus geen onterechte "opgeslagen"-melding vóór het tabletantwoord. Toon verzonden/wachten, bevestigd, afgewezen en verlopen zichtbaar.
- Behoud bestaande payloadtypen, veldnamen, min/max, defaults en escapes; maak geen ongevraagde contractbreaking wijzigingen.

## 5. Belangrijke technische eisen voor het UI-herontwerp

- Rework de frontend zonder alle gebruikersinput bij polling te vernietigen.
- Behoud actieve tablet, tab/sectie, scrollpositie, focus en **niet-opgeslagen** draft-settings.
- Verwerk late of herhaalde MQTT-responses zonder de editor te overschrijven.
- Geef feedback bij mislukte HA-servicecalls en laadfouten **in de UI**; niet alleen console.error.
- Houd kiosk-IDs en andere uit MQTT afkomstige strings goed ge-escaped; behoud de bestaande _escape of een even veilig alternatief.
- Toetsenbordgebruik, aria-labels, focus-visible, kleurcontrast en grote touch targets.
- Geen externe frontendbibliotheken of build-chain introduceren tenzij nodig en goed toegelicht; huidige frontend is een standalone Web Component.
- Test geen echte garage-/camera-acties in productie; gebruik mocks of gesimuleerde data.

## 6. Branding: iconen en de HA-vs-HACS-vraag

De gebruiker heeft om passende iconen gevraagd omdat eerder op HACS/Marketplace en in het HA-menu geen herkenbaar merklogo stond.

Er is al een icoonontwerp gemaakt in zwart/antraciet met oranje smart-homehuis binnen een tablet. De huidige publieke bestanden in **brand/** en **frontend/icon.png** horen bij deze taak; **maak niet blind nieuwe iconen voordat ze zijn bekeken**.

Controlepunten voor de volgende agent:
- Test of de integratietegel onder **Instellingen → Apparaten en diensten** brand/icon.png en icon@2x.png toont op ondersteunde HA-versies.
- Controleer of de exacte HACS-/Marketplace-versie deze lokale brandbestanden ondersteunt. Als klassieke HACS de lokale assets niet toont, onderzoek de ondersteunde brand/discovery-route in plaats van een custom frontend-hack voor te stellen.
- Het zijmenu gebruikt in de huidige backend **mdi:tablet**. Het paneel kan desgewenst frontend/icon.png tonen; een eigen PNG als sidebar_icon wordt niet gegarandeerd door panel_custom. Maak geen ongefundeerde belofte.
- Beoordeel in het paneel of grotere logo's ook in licht/donker voldoende contrast en ruimte hebben.
- **CI was na de PNG-publicatiescanfix weer groen**; houd het beperkte bestandspadallowlist aan.

## 7. Wat uit de private Android-ontwikkeling relevant is, maar NIET in deze publieke integratie zit

Er is in de experimentele Gecko-app gewerkt aan:
- offline pagina en reconnect wanneer HA bij opstart onbereikbaar is;
- lokale settingspagina met tandwiel rechtsboven in donker/oranje thema;
- linkerrand-swipe naar rechts als native terugactie;
- optionele 4-cijferige PIN voor de lokale settings (standaard UIT);
- via MQTT publiceren van settings-/beveiligingsaudit-events.

Deze Android-functies zijn **afzonderlijke private code** en waren bij dit handoff niet volledig op echte SM-T580-hardware bewezen. De publieke HA-integratie bevat nog geen beheerinterface voor al die mogelijke functies. Voeg geen status of UI-controls toe zonder bestaand bron-/MQTT-contract en tests.

Ook is besproken dat de **HA-integratie later een OTA-broker** wordt: ze haalt een goedgekeurde APK vanuit een privébron op en streamt die naar een tablet met verificatie, voortgang en Android-installatiecontrole. Dit is een toekomstwens; **niet geïmplementeerd** en buiten de huidige UI-redesign. De private repository mag hiervoor privé blijven.

## 8. Publicatie- en privacycriteria

- Alleen de publieke integratie wijzigen; kopieer geen hele private codebase.
- Geef geen echte IP-adressen, SSID, camera-URL, dashboard-URL, serienummers, persoonlijke links of Android-debuglogs vrij.
- De publieke scanner is een extra filter, geen vervanging voor handmatige inspectie en diff-review.
- Publicatie als HACS-customrepo moet eenvoudig blijven; geen speciale installatiestappen vereist.
- Android APK's en private GitHub Actions-buildartifacts blijven voorlopig buiten de publieke release.
- Geen licentie toevoegen voordat de eigenaar beslist welk opensourcelicentiebeleid gewenst is.

## 9. Acceptatie en regressietests

1. Dashboard overzicht overzichtelijk met 0, 1 en meerdere kiosken.
2. Online, offline en onbekende status correct en zonder misleidende aannames.
3. Alle bestaande camera- en screensaverknoppen doen dezelfde servicecalls als vroeger.
4. Settings worden opgehaald, aangepast, per sectie verzonden, bevestigd, fout gemeld en gereset; de request_id/timeout-semantiek blijft correct.
5. Elke 2 seconden verversen zonder de invoer, focus, tab of scrollpositie kwijt te raken.
6. Goede mobiele indeling, normale toetsenbordnavigatie en licht/donker HA-thema.
7. Integratielogo, zijmenuicoon en HACS-weergave apart controleren en beperkingen eerlijk melden.
8. Publieke CI en publicatie/privacychecks blijven groen.
9. Bij voorkeur frontend-DOM-tests met synthetische data toevoegen; bestaande unittest is een **protocolmock** en geen echte Home Assistant-browsertest.
10. Herstart/installatie van HACS-customrepo met het nieuwe manifest en actuele versie testen; alleen claims doen die feitelijk gecontroleerd zijn.

## 10. Concreet werkplan voor Codex

- Lees eerst deze handoff, README.md, docs/PUBLISHING.md, manifest.json, services.yaml, __init__.py en frontend/ha-gecko-kiosk-panel.js.
- Controleer actuele HEAD en CI-status voor je wijzigingen.
- Maak een featurebranch voor het **UI-herontwerp** in de publieke repo; werk in kleine reviewbare commits.
- Verbeter de layout en stateflow zoals hierboven, zonder extra MQTT-commandofuncties te verzinnen.
- Verwerk bestaande branding en controleer HA-sidebar/Marketplace-beperkingen.
- Voeg testbare component- of DOM-regressiechecks toe, run bestaande CI, controleer de publieke diff op persoonlijke gegevens.
- Lever een PR met screenshots **uitsluitend op basis van fictieve demo-data**, testresultaten, bekende beperkingen en een duidelijk changelog.
- Zet niet eigenmachtig de private repo publiek; merge niet zomaar naar publieke main als de eigenaar eerst het resultaat wil zien.

## 11. Direct te gebruiken Codex-startopdracht

> Werk in de publieke GitHub-repository Alec-99/Alec-99-ha-gecko-kiosk. Lees eerst docs/HANDOFF_CODEX_UI_BRANDING_2026-11-06.md en docs/PUBLISHING.md. Leg uit waarom de private ontwikkelrepo en de publieke distributierepo bewust gescheiden zijn. Implementeer de HA-beheer-UI-redesign op een aparte branch met tabs/secties, stabiele polling, behoud van settingsdrafts en correcte MQTT-ACK-feedback. Controleer de bestaande iconen, HACS-/HA-weergave en toegankelijkheid. Respecteer de bestaande servicecontracten en de privacy-allowlist. Voeg tests toe, voer de publieke CI uit en maak een reviewbare PR. Importeren van private Git-geschiedenis, diagnostiek en configuratie is verboden. Benoem eerlijk wat niet met een echte Home Assistant-instantie is getest.
