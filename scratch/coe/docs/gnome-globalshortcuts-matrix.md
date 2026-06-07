# GNOME GlobalShortcuts Matrix

## Purpose

This document tracks what is actually known about `org.freedesktop.portal.GlobalShortcuts` support on GNOME.

It separates:

- verified local observations
- official upstream statements
- inferences that still need on-device validation

That distinction matters because GNOME support depends on more than one version number:

- GNOME Shell / Mutter
- `xdg-desktop-portal`
- `xdg-desktop-portal-gnome`
- the exact distro packaging state

## Current verified local result

Verified on the development machine for this repository:

- OS: Ubuntu 24.04.4 LTS
- session: `XDG_SESSION_TYPE=wayland`
- desktop: `ubuntu:GNOME`
- `gnome-shell`: `46.0-0ubuntu6~24.04.13`
- `xdg-desktop-portal`: `1.18.4-1ubuntu2.24.04.1`
- `xdg-desktop-portal-gnome`: `46.2-0ubuntu1`

Observed via native D-Bus probe and cross-checked with `gdbus`:

- `org.freedesktop.portal.RemoteDesktop`: present, version `2`
- `org.freedesktop.portal.Clipboard`: present, version `1`
- `org.freedesktop.portal.GlobalShortcuts`: not present

Implication:

- GNOME 46 on Ubuntu 24.04 is not a sufficient target for portal-backed global hotkeys.
- This environment must currently run in degraded mode.

## Upstream timeline

### 2024-05-24: not ready yet

GNOME's "This Week in GNOME" on 2024-05-24 described ongoing work and said the settings work had to be shuffled around "before the globalshortcuts part can go in".

Interpretation:

- During the GNOME 46 timeframe, the feature was still in progress.

Source:

- https://thisweek.gnome.org/posts/2024/05/twig-149

### 2025-02-28: support announced

GNOME's "This Week in GNOME" on 2025-02-28 said:

- the GNOME desktop portal now supports the `Global Shortcuts` interface
- applications can register desktop-wide shortcuts
- users can edit and revoke them through system settings

Interpretation:

- By late February 2025, GNOME upstream considered `GlobalShortcuts` support landed.

Source:

- https://thisweek.gnome.org/posts/2025/02/twig-189/

### GNOME backend release windows

Official GNOME source indexes show:

- `xdg-desktop-portal-gnome` `46.2` published on `2024-05-25`
- `xdg-desktop-portal-gnome` `47` series published before the February 2025 announcement
- `xdg-desktop-portal-gnome` `48.beta` published on `2025-02-03`
- `xdg-desktop-portal-gnome` `48.rc` published on `2025-03-01`
- `xdg-desktop-portal-gnome` `48.0` published on `2025-03-17`

Sources:

- https://download.gnome.org/sources/xdg-desktop-portal-gnome/46/
- https://download.gnome.org/sources/xdg-desktop-portal-gnome/48/
- https://download.gnome.org/sources/xdg-desktop-portal-gnome/

## Working matrix

| GNOME family | Expected status | Confidence | Reason |
| --- | --- | --- | --- |
| 46.x | no `GlobalShortcuts` in practice | high | Verified locally on Ubuntu 24.04 with `gnome-shell 46.0`, `xdg-desktop-portal 1.18.4`, `xdg-desktop-portal-gnome 46.2` |
| 47.x | unclear, likely not a safe baseline | low | Upstream support was only publicly announced on 2025-02-28, late in the 47 cycle; no local verification yet |
| 48.x | likely the first viable baseline | medium | The announcement happened during the 48 release window, and 48 prereleases / final releases line up with that timing |
| 49+ | expected to support it | medium | Follows the post-landing release family, but still needs real-machine validation |

## Engineering decision

For this project, treat the GNOME target as:

- minimum **design target**: GNOME 48-era portal stack
- minimum **verified target today**: none yet

That means:

- do not promise portal-backed global hotkeys on Ubuntu 24.04 / GNOME 46
- keep `doctor` as the source of truth for the local machine
- keep an external-trigger fallback for older GNOME deployments

## What must be validated next

Before claiming GNOME support for release notes or README:

1. Run `coe doctor` on a GNOME 48 or newer machine.
2. Confirm that `org.freedesktop.portal.GlobalShortcuts` is present.
3. Record the reported interface version.
4. Record the exact distro package versions for:
   `gnome-shell`, `mutter`, `xdg-desktop-portal`, `xdg-desktop-portal-gnome`
5. Confirm whether press/release events are delivered as `Activated` / `Deactivated`.

## Practical release stance

Until step 1 through 5 are done, the honest product statement is:

- GNOME support is implemented as a portal-first architecture.
- GNOME 46 on Ubuntu 24.04 is verified to lack `GlobalShortcuts`.
- GNOME 48+ is the expected support baseline, but still requires direct validation on target machines.
