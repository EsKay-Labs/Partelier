# Fan references and shaded preview — 0.29.1

The **?** beside Fan style opens a real Fusion rendering of that preset and a
short explanation. The same dialog offers all eight families, each with its own
image and question control. Browsing these references does not change settings,
start a native command or compute a preview. Images are bundled locally, so the
help works before New fan and without Fusion connectivity. Parameter-specific
help retains its explanatory dimension diagrams.

The pictures are actual generated presets, not predictions of the current
custom dimensions. Axial, wide, slim, ring, 2/3/4-blade propellers and radial
blower each have their own image. The dialog explicitly identifies these as
example models.

## Preview appearance

The supplied screenshot showed Fusion's AppearanceColorEffect rendering the
exported fan mesh almost flat. Fan meshes now use BasicMaterialColorEffect with
explicit diffuse/ambient/specular lighting, zero emission and full opacity. The
base colour comes from the existing appearance (including saved fan body colours
during Edit), with neutral grey as fallback. The effect is intended for clear
CAD shading; it does not reproduce texture maps or photoreal material rendering.
It creates no document appearance, changes no material and retains cached mesh
normals and edge outlines. Other tools retain their existing effect selection.

## Verification and limits

- 1,196 Python tests and six Node suites pass. Help tests browse all eight images
  before any native fan request and check that settings remain unchanged.
- Headless Edge checks at 300/380/520 px pass with decoded images, working gallery,
  no horizontal overflow and no JavaScript errors.
- A first native batch in Fusion 2706.1.14 generated all eight images and checked
  opaque lit meshes, unchanged history/body counts and no new appearances.
- The final lower ambient-light setting was checked on an axial rotor, with
  captured normal-body and mesh-preview images. Existing live preview graphics
  also showed the lighting difference without rebuilding geometry.
- A subsequent bulk rerender disconnected and produced an Autodesk crash report.
  Its cause was not established. Bulk rendering is now disabled in the opt-in
  fixture; one explicit style is required, with child wrappers released before
  document closure. No further bulk geometry test was attempted. This is not
  evidence that every possible Fusion graphics failure has been eliminated.
- After Fusion restarted, 0.29.1 loaded with a valid visible palette and unchanged
  caller state. See the saved startup and UI reports in `docs/validation`.

`tools/fusion/FanVisualValidation.py` is an opt-in asset/validation tool, never a
runtime help action. The gallery displays PNG files only.
