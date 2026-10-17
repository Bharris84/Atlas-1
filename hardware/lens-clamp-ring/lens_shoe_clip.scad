// Snap-on lens clip with a shoe slot
// ----------------------------------
// A C-shaped clip that snaps over the fixed part of a lens barrel (no
// screws) and carries an ISO 518 shoe slot on top, so a monitor or
// teleprompter sits right above the lens. Made for short lenses such as
// the Canon EF-S 24mm f/2.8 STM pancake, where there is only a narrow band
// of fixed barrel between the mount and the focus ring: the clip grips that
// band and the shoe platform reaches forward over the focus ring without
// touching it.
//
// Coordinate system: lens axis = Y, with Y = 0 at the rear face (camera
// side) and +Y towards the front of the lens. The clip opening faces -Z.
//
// Print standing on its rear face (the face that goes against the camera).
// Every layer is then a complete C, which is what makes it flex without
// cracking, and the shoe slot prints with no supports.
// PLA is fine for a light monitor; PETG is more forgiving if it gets snapped
// on and off a lot. Line the bore with ~1 mm rubber tape so it grips.

/* [What to render] */
// clip = the part; size_test = four thin C-rings with different bores, to
// find the snug fit fast (1 to 4 notches on the outside = smallest to largest)
part = "clip"; // [clip, size_test]
// Bores tried by size_test: size_test_start, +step, +2*step, +3*step
size_test_start = 67.0;
size_test_step = 0.5;

/* [Lens] */
// Diameter of the fixed barrel where the clip sits (measure it)
lens_d = 68.2;
// Liner thickness (rubber tape / felt). 0 = bare plastic
liner_t = 1.0;
// How much smaller the bore is than lens + liner, so the clip squeezes
grip = 0.3;
// Set this to override the bore diameter directly (e.g. the size that fit
// best in size_test); 0 = lens_d + 2 * liner_t - 2 * grip
bore_d = 0;

/* [Clip] */
// Width of the band that grips the barrel; must fit between the mount and
// the focus ring without touching either
band_w = 8;
// Radial wall thickness of the C
wall = 4;
// How far the C wraps around the barrel (degrees); >180 so it snaps on
wrap = 220;

/* [Shoe platform] */
// Platform length along the lens, measured forward from the rear face
platform_len = 22;
platform_w = 26;
// Gap between the platform underside and the lens in front of the band
lens_clear = 3;

/* [Shoe slot (ISO 518)] */
shoe_tol = 0.4;
shoe_foot_w = 18.0;
shoe_foot_t = 2.0;
shoe_open_w = 12.6;
shoe_rail_t = 2.5;
// Plastic under the shoe channel
shoe_floor = 3;
// Thickness of the end stop at the rear (camera) end; the slot is open at
// the front so the foot slides in from the front of the lens
shoe_stop = 3;

/* [Hidden] */
$fn = 160;
eps = 0.01;

lens_r = lens_d / 2;
inner_r = bore_d > 0 ? bore_d / 2 : lens_r + liner_t - grip;
outer_r = inner_r + wall;

ch_w = shoe_foot_w + shoe_tol;
ch_h = shoe_foot_t + shoe_tol;
plat_bottom = lens_r + lens_clear;
ch_z = max(plat_bottom, outer_r) + shoe_floor;
plat_top = ch_z + ch_h + shoe_rail_t;

assert(wrap > 180 && wrap < 300, "wrap should be between 180 and 300 degrees");
assert(platform_len >= band_w, "platform_len must be at least band_w");
assert(platform_w >= ch_w + 4, "platform_w too narrow for the shoe channel");
assert(platform_len - shoe_stop >= 15, "platform too short for a shoe foot");

// 2D C profile, opening centred on -Z (2D Y here is Z in the part)
module c_profile(inner_r = inner_r, outer_r = outer_r) {
    gap = 360 - wrap;
    tip_r = wall / 2;
    mid_r = (inner_r + outer_r) / 2;
    difference() {
        circle(r = outer_r);
        circle(r = inner_r);
        // wedge removing the opening
        rotate(-90 - gap / 2)
            polygon([[0, 0],
                     for (a = [0 : gap / 8 : gap]) 2 * outer_r * [cos(a), sin(a)]]);
    }
    // rounded tips so it slides on without catching
    for (s = [-1, 1])
        rotate(-90 + s * gap / 2) translate([mid_r, 0]) circle(r = tip_r, $fn = 48);
}

module shoe_cut() {
    // channel for the foot, open at the front
    translate([-ch_w / 2, shoe_stop, ch_z]) cube([ch_w, platform_len, ch_h]);
    // opening between the rails
    translate([-shoe_open_w / 2, shoe_stop, ch_z]) cube([shoe_open_w, platform_len, plat_top]);
    // lead-in chamfer at the front of the rails
    translate([0, platform_len + eps, plat_top])
        rotate([90, 0, 0])
            linear_extrude(height = 1.5, scale = [shoe_open_w / (shoe_open_w + 3), 1])
                square([shoe_open_w + 3, 2 * shoe_rail_t + 0.2], center = true);
}

module clip() {
    difference() {
        union() {
            // the C band
            rotate([-90, 0, 0]) mirror([0, 1, 0])
                linear_extrude(height = band_w) c_profile();
            // shoe platform: joined to the band at the rear, cantilevered
            // forward above the focus ring
            hull() {
                translate([-platform_w / 2, 0, plat_bottom])
                    cube([platform_w, platform_len, plat_top - plat_bottom]);
                // gusset down onto the band
                translate([-platform_w / 2 - 4, 0, outer_r - wall])
                    cube([platform_w + 8, band_w, eps]);
            }
        }
        // keep the bore clear (the hull would otherwise fill it)
        rotate([-90, 0, 0]) translate([0, 0, -1])
            cylinder(r = inner_r, h = platform_len + 2);
        // and keep the platform off the lens in front of the band
        translate([0, band_w, 0]) rotate([-90, 0, 0])
            cylinder(r = plat_bottom, h = platform_len);
        shoe_cut();
    }
}

// Thin test ring with n notches on the outside of its crown
module test_ring(bore, n) {
    difference() {
        linear_extrude(height = 4) c_profile(bore / 2, bore / 2 + wall);
        for (i = [0 : n - 1])
            rotate(90 + (i - (n - 1) / 2) * 6)
                translate([bore / 2 + wall, 0, -1]) cylinder(r = 1, h = 6, $fn = 16);
    }
}

if (part == "size_test") {
    pitch = size_test_start + size_test_step * 3 + 2 * wall + 6;
    for (i = [0 : 3])
        translate([(i % 2) * pitch, floor(i / 2) * pitch, 0])
            test_ring(size_test_start + i * size_test_step, i + 1);
    for (i = [0 : 3])
        echo(str(i + 1, " notch(es): bore ", size_test_start + i * size_test_step, " mm"));
} else {
    clip();
    // ghost of the lens barrel
    %rotate([-90, 0, 0]) translate([0, 0, -5]) cylinder(d = lens_d, h = platform_len + 10);
}

echo(str("Bore = ", 2 * inner_r, " mm (lens ", lens_d, " + liner, minus grip)"));
echo(str("Snap opening = ", 2 * inner_r * sin((360 - wrap) / 2), " mm"));
echo(str("Shoe top is ", plat_top - lens_r, " mm above the lens surface"));
