# Publicatiebeleid / Publishing policy

**Private development repository → manually approved public snapshot.** Dit is geen fork of mirror. Kopieer geen private Git commits, systeemlogs, screenshots, APKs, echte configbestanden of persoonlijke links.

## Allowlist voor synchronisatie

Alleen de onderstaande bronpaden mogen na broncodecontrole worden gepubliceerd:

- `home-assistant/custom_components/ha_gecko_kiosk/**` → `custom_components/ha_gecko_kiosk/**`
- `tests/ha_gecko_kiosk/test_protocol.py` → publieke tests (met aangepaste importlocatie)
- De expliciet gecontroleerde projectidentiteit: `assets/brand/icon.svg`, `assets/brand/icon-512.png`, `assets/brand/github-social-1280x640.png` en `assets/brand/github-readme-banner-1600x400.png`; de drie rasterbestanden staan ook expliciet met verwachte dimensies in `scripts/check_public_snapshot.py`.
- Publieke README, `hacs.json`, CI en documentatie, afzonderlijk gereviewd

Voor elke nieuwe push: selecteer private commit, controleer alle gewijzigde bestanden op authenticatiegegevens, lokale adressen, interne SSIDs, identificatiegegevens en persoonsinformatie; voer CI uit; bekijk de publieke diff en geef expliciet vrij. **Nooit automatisch alle private wijzigingen doorpushen.**

De publicatiechecker laat geen willekeurige afbeeldingen toe. Alleen expliciet genoemde merkmiddelen zijn toegestaan; screenshots, foto's en overige binaire bestanden blijven geblokkeerd.

## Versionering

De integratieversie staat in `custom_components/ha_gecko_kiosk/manifest.json`; Android APK-versies zijn onafhankelijk. Een publieke GitHub Release pas na testen met een echte HA-installatie.

## Licentie

De projecteigenaar heeft nog geen licentie gekozen. Publicatie van broncode staat geen herdistributie toe zonder expliciete licentie. Kies eerst een licentie voordat je het project als opensource verspreidt.
