# Public brand assets

This public integration repo includes only the assets needed by the HA panel and repository page, curated from the user-supplied Universal Brand Kit v2:

- `icon-512.png` and `icon.svg` for Gecko identity and reuse
- `github-readme-banner-1600x400.png` for this repository README
- `github-social-1280x640.png` as the repository social-preview candidate
- the color and identity references used by the public panel

Android app resources, store templates, and unrelated platform exports stay in the private Gecko development repository. The screenshot-template images from the source package are not published as product screenshots.

The integration's `brand/icon.png` (256 px) and `brand/icon@2x.png` (512 px) use the same approved dark icon as `frontend/icon.png` and `icon-512.png`. Functional panel symbols and the sidebar continue to use Home Assistant's Material Design Icons.

Home Assistant versions with the local brands API serve installed custom integration images from `brand/` before consulting the external catalog; missing dark variants fall back to these icon files. This path was checked against the upstream `homeassistant/components/brands` and loader source. Older Home Assistant/HACS versions that use the external catalog directly may still need catalog support; the shipped files alone cannot update that service. Visibility in a live Home Assistant installation has not been verified here.

After downloading an updated integration, restart Home Assistant and reload the browser page to load the registered frontend module and icon assets.
