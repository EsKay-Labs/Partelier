"""Lit opaque fan meshes, without creating document appearances or solids."""

def material(appearance, core, native):
    # Appearance effects can render exported custom meshes unlit in Fusion.
    # Retain the appearance's base colour, but explicitly request Phong lighting.
    rgb=(160,160,160)
    if appearance is not None:
        for identity in ('generic_diffuse','metal_f0','opaque_albedo','surface_albedo'):
            prop=core.ColorProperty.cast(appearance.appearanceProperties.itemById(identity))
            if prop is not None:
                value=prop.value
                rgb=(value.red,value.green,value.blue)
                break
    diffuse=core.Color.create(*rgb,255)
    effect=native.CustomGraphicsBasicMaterialColorEffect.create(
        diffuse,core.Color.create(*(round(channel*.25) for channel in rgb),255),core.Color.create(220,220,220,255),
        core.Color.create(0,0,0,255),35.,1.)
    if effect is None:raise ValueError('Fusion could not create the shaded fan preview.')
    return effect
