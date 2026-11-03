# Overnight implementation — 0.28.0

## Scope and status

The user authorized unattended implementation and script-driven checks, followed
by their own physical/interactive tests. Hardware pockets remain excluded by
their earlier instruction. All native checks use disposable documents and restore
the caller; no mouse/keyboard automation is used.

| Menu | Added capabilities | Boundary |
|---|---|---|
| Mechanical pairs | Straight and dovetail guides with optional stop; bayonet; clevis; barrel and recessed single-axis hinges | Separate mating bodies at origin plus XYZ offset. These do not automatically attach to existing parts. |
| Mechanical pairs | Captive hinge and captive louvers | Explicit print trials. No physical release/friction validation. Louvers have separate movable vanes, no linked register actuator. |
| Face details & labels | Finger notch, keyhole, fixed stop, text, arrow, graduated ticks | Attached to one selected planar face. Notch requires a rectangular outside boundary. |
| Fans & Propellers | Radial blower impeller | Backplate, hub, radial vanes. No volute housing or motor. |
| Lid lip & groove | Circular and convex polygon continuous perimeters | Exact circles and 3–10 straight-sided convex outlines. Selected sides remain rectangular; concave/spline outlines are refused. |

New tools retain the palette workflow, cached mesh preview, Cancel, saved recipes
and guarded Edit/Delete. Body ownership is deliberate: face details modify the
selected source; mechanical pairs and rotors create separate parts. Settings
remain local. No performance, fit, sealing, strength or airflow rating is implied.

## Morning test sequence

1. Open a disposable design; the loaded build should read **0.28.0** in About.
2. **Mechanical pairs** → Straight guide → New mechanism. Change clearance and
   stop, Create, then use the section's Saved features to Edit and Delete. Repeat
   for Dovetail, Bayonet and Clevis. Existing design geometry is not required.
3. Try the three hinge choices. The recessed choice is single-axis geometry for
   recessed installation, not a concealed multi-link furniture hinge. Review
   the captive hinge in the slicer; its entire underside is not certified45°.
4. Try **Captive louvers · print trial** at its defaults, with the frame back on
   the bed. Print a small coupon first. Each vane moves independently; there is
   no common adjustment lever.
5. Draw a simple solid rectangular plate. In **Face details & labels**, select
   its planar face and try each type. Position adjusts local X/Y; notch Boundary
   side chooses its rim. Keyhole depth is an explicit cut depth, not automatic
   through-all. Text/arrow/scale support engraved and raised modes.
6. For **Lid lip & groove**, prepare separate base/lid solids with facing planar
   circular or convex polygon faces. Choose Continuous perimeter. Create and
   Edit; check clearance and floor protection on your actual wall thickness.
7. In **Fans & Propellers**, choose **Radial blower impeller**, then a size or
   Custom. Adjust vane height, vane thickness and backplate; shaft fit has a
   separate small hub coupon. No operating RPM has been established.
8. For each workflow, test Cancel, Close, Saved Edit/Delete, then save/reopen a
   disposable file. Physical printing and real pointer acceptance belong to
   this user test; headless CAD checks do not establish either.

## Deferred scope

Automatic attachment/placement of the new mechanical pairs, multi-link concealed
hinges, a linked register damper, blower volute housing, general concave/spline
lips and automatic upstream recomputation are not implemented in this build.
Explicit Rebuild remains the contract. Hardware pockets remain excluded.

## Verification completed

1171 Python tests and six Node UI suites pass. Headless Edge checks all13 menu
entries at300/320/380/520px without overflow or JavaScript errors. Native Fusion
2706.1.14 checks eight mechanical families, their sampled motions, blower
creation/rebuilding/deletion, six face-detail creation/edit cases (including
engrave-to-emboss), three face-detail preview/delete restorations, four notch
sides, and circular/hexagonal lip creation/edit/deletion with floor guards.
Production command sessions also pass asynchronous Preview/Create and
Preview/Cancel for the new managers. Startup loads0.28.0 and the original caller
body/history/visibility state is restored. This does not establish save/reopen,
Undo/Redo across every new family or physical print acceptance.
