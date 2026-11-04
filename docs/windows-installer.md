# Windows installation — 0.32.0

Partelier is an Autodesk Fusion add-in, not a standalone CAD application.
The Windows EXE installs for the current Windows user without elevation into:

`%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\Partelier`

Save and close Fusion before installing, updating or uninstalling. Setup checks
for Fusion and refuses to modify files while it runs; it never terminates Fusion.
Run `Partelier-0.32.0-Windows-Setup.exe`, then reopen Fusion and click
**Design → Utilities → Add-Ins → Partelier**. The approved FIT emblem identifies
the command. Partelier registers silently at startup, including repeated Run;
opening the HTML palette requires the command.

If absent, use Fusion's Scripts and Add-Ins dialog to run Partelier and enable
Run on Startup. A previously saved Fusion startup preference may override the
new manifest default. Existing developer/manual registrations in other folders
should be stopped and disabled before using an installed copy; setup does not
delete or rewrite those checkouts or Fusion preferences.

Updates use the same application identity and destination. Setup refuses to
overwrite a destination without its ownership marker. Back up or move a previous
manual install yourself before replacing it. Windows Installed Apps provides
**Partelier for Autodesk Fusion → Uninstall**. Removal targets installer-owned
files, not user CAD documents or unrelated add-ins.

The ZIP is an alternative manual bundle. It contains the same runtime assets,
without developer fixtures, test scripts or Python caches. Do not run two copies
of the add-in. Fusion supplies Python and the CAD API; no separate Python install
is required by end users. This release targets Windows10/11 x64 with Autodesk
Fusion; it is not a macOS installer.

Release checksums accompany the EXE and ZIP. The installer has no Authenticode
signature because no publisher signing certificate is configured; Windows may
display an unknown-publisher or reputation prompt. A checksum verifies the
download against the published release, not publisher identity.

## Build

Use Python3 and an installed Inno Setup6+ compiler:

```powershell
python tools/build_installer.py --iscc 'C:\Path\To\ISCC.exe'
```

Outputs are in `dist/`. The builder stages only runtime files from `Partelier/`,
adds the installation note/icon and generates SHA-256 checksums. The installer
uses a separate test application identity for isolated smoke tests beneath
`%TEMP%\PartelierInstallerTest\`; that path does not modify the live add-in.

Native Fusion checks verified quiet initial/repeated registration, icon resources,
explicit launcher opening and unchanged caller geometry. Installer checks are
recorded in [validation](validation/installer-0.32.0.json); they do not represent
testing every Windows/Fusion configuration.
