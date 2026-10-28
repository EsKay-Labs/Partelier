# Fans & Propellers implementation

## Goal
Implement approved A–G axial PC rotors and air propellers in an independent tool.
Blower H is a later phase. Presets are dimensional starting points, not tested
airflow/pressure/noise or strength ratings. Motor hub interfaces remain measured.

## Delivery
1. Strict standalone settings, dimensional PC presets, bounded blade sections,
   root/middle/tip chord and twist, pitch mode, sweep, camber and thickness.
2. One native blade solid repeated around a bored or D-shaft hub; root blend,
   optional rotating tip ring, optional mounting frame/guard and hub-only coupon.
   Native prototype precedes selecting the solid construction path.
3. HTML-only grouped controls with actual illustrations/help, optional circular
   opening fit and custom sketch outline, cached preview and cancellation.
4. One owned BaseFeature containing independent generated bodies; exact recipes,
   guarded in-place Rebuild and Saved features Edit/Delete. Preserve source CAD.
5. Local numerical/protocol/UI tests, small isolated Fusion tests of A–G,
   custom values, fitting, frame/coupon, preview cleanup and Edit/Delete.

## Constraints
Reuse the existing rollback compute runner and opaque display mesh. No custom
graphics BRep bodies, native per-blade history features, new runtime packages,
or per-orbit computation. Geometry is in millimetres until the Fusion boundary.
Model/reference edits must invalidate cached previews. Unsupported combinations
fail with actionable messages; do not silently reduce requested geometry.
Keep the existing 380px workflow and all existing tool settings/recipes intact.
The user approved normal generation and native script tests, not physical fan
operation; performance, strength and balance require physical validation.

## Delivery status
A–G delivered in0.27.0. Local and isolated native checks are recorded in
[the validation report](validation/fans-0.27.0.json); usage and limits are in
[Fans & Propellers](fans-and-propellers.md). H remains deferred.
