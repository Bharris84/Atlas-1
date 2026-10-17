# Lens clamp ring with shoe / 1/4"-20 mount

`lens_clamp_ring.scad` is a parametric, two-piece ring that bolts around a lens barrel. It carries one of these mounts on top:

| `mount_type` | What you get |
|---|---|
| `shoe` | ISO 518 cold/hot-shoe slot (accepts a standard shoe foot) |
| `quarter20` | Flat pad with a 1/4"-20 mount |
| `both` | Shoe slot with a 1/4"-20 hole in its floor |

For the 1/4"-20 mount, `quarter20_style` picks how the thread is made:

- `insert`: a 1/4"-20 heat-set insert (check `insert_hole_d` against your insert's datasheet).
- `nut`: a captive 1/4"-20 hex nut that slides in from the back face.
- `tap`: a #7 (5.1 mm) pilot hole that you tap yourself.

With `cable_tie = true` (the default), one ear gets a zip-tie slot for anchoring a power cord.

## Usage

1. Use calipers to measure the barrel where the ring will sit. Pick a spot that doesn't rotate, never the zoom or focus ring. Set `lens_d` to that measurement. The presets are Canon's maximum diameters, so treat them only as a starting point.
2. Print `part = "fit_test"` first. It's a thin slice of both halves with no mount on top, so it prints quickly. Bolt it on with the liner in place. If it's loose or won't close, adjust `lens_d` (or `liner_t`) and test again.
3. Open the file in OpenSCAD and use the Customizer to set the mount type and style. Then set `part = "plate"` and export an STL.
4. Print in PETG, ASA or ABS, with 4+ perimeters and 30–40% infill. PLA works for light loads that stay out of heat; don't overtighten the screws. Print both halves split-face down; the plate layout already does this.
5. Line the bore with 1 mm felt or rubber tape. Then bolt the halves together with 2× M4×16 socket-head screws and nuts. The `clamp_gap` setting makes the halves squeeze the liner as you tighten.

From the command line:

```sh
openscad -o ring.stl -D 'part="plate"' -D 'lens_d=88.5' -D 'mount_type="both"' lens_clamp_ring.scad
```

**Load warning:** a lens barrel isn't built to carry weight. Use this ring for light loads, such as a phone or tablet teleprompter. A full-size teleprompter should sit on 15 mm rods or a rail, not on the lens.

## Snap-on shoe clip (short / pancake lenses)

`lens_shoe_clip.scad` is a screwless alternative for lenses with only a narrow band of fixed barrel, such as the EF-S 24mm f/2.8 STM. It's a C-clip that wraps 220° around the barrel and snaps on. A shoe platform on top reaches forward over the focus ring without touching it. The shoe slot opens toward the front of the lens, so the foot slides in from the front.

- Set `lens_d` to the barrel diameter. Set `band_w` to the clear length between the mount and the focus ring, minus about 1 mm.
- Print it standing on its rear face, the side that goes against the camera. No supports are needed.
- Line the bore with about 1 mm of rubber tape so it grips.
- If the fit is off, print `part = "size_test"` (`stl/efs24_stm_size_test.stl`). It's four thin C-rings with bores of 67.0, 67.5, 68.0 and 68.5 mm, marked with 1 to 4 notches. Set `bore_d` to the one that snaps on snugly, then print the clip.

`stl/efs24_stm_shoe_clip.stl` is ready to print for the EF-S 24mm f/2.8 STM. It has an 8 mm band and a 66.75 mm bore for a bare-plastic fit, with no liner needed.
