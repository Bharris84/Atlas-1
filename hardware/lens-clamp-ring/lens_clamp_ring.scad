// Lens clamp ring with cold/hot-shoe slot and/or 1/4"-20 mount
// ---------------------------------------------------------------
// A two-piece clamp that bolts around a Canon (or any) lens barrel and
// carries an accessory mount on top: an ISO 518 shoe slot (accepts the
// foot of a teleprompter, light, mic, etc.), a 1/4"-20 threaded mount, or
// both (shoe slot with a 1/4"-20 hole in its floor).
//
// Coordinate system: lens optical axis = Y. The split line is horizontal
// (Z = 0), clamp bolts run vertically through the side ears, and the
// accessory mount sits on top of the upper half.
//
// MEASURE YOUR LENS with calipers at the spot where the ring will sit
// (a non-rotating part of the barrel — never on the zoom or focus ring).
// The presets below are Canon's published *maximum* diameters and are only
// a starting point; the barrel is often narrower where you clamp.
//
// Print in PETG, ASA or ABS (PLA creeps under clamp load and in a hot car).
// 4+ perimeters, 30-40% infill. Line the bore with 1 mm adhesive felt or
// rubber tape (or print a TPU band) so the ring grips without marking the lens.
//
// Hardware: 2x M4 socket-head screws (length ~ 2*ear_t, 16 mm by default)
// + 2x M4 hex nuts. For the 1/4"-20 mount: a 1/4"-20 heat-set insert,
// a 1/4"-20 hex nut, or tap the hole directly (see quarter20_style).

/* [What to render] */
// assembly = preview with both halves; plate = both halves laid out for printing;
// fit_test = thin, mount-less slice of both halves to check the bore size fast
part = "assembly"; // [assembly, top, bottom, plate, fit_test]

/* [Lens] */
// Pick a preset or "custom" and set lens_d yourself
lens_preset = "custom"; // [custom, EF 24 f/2.8 IS USM, EF 24 f/1.4L II, EF 24-70 f/2.8L II, EF 70-200 f/2.8L IS II/III, EF 24-105 f/4L IS, RF 24-70 f/2.8L IS, RF 24-105 f/4L IS, EF 50 f/1.8 STM]
// Measured barrel diameter at the clamp location (mm)
lens_d = 83.5;
// Liner thickness inside the bore (felt / rubber / TPU). 0 = bare plastic
liner_t = 1.0;
// Material removed from the split faces in total; this is the clamp squeeze
// applied to the liner when the bolts are tightened
clamp_gap = 1.0;

/* [Ring] */
// Radial wall thickness
wall = 5;
// Axial width of the ring (along the lens)
ring_w = 22;
// Ear thickness per half (vertical, at the clamp bolts)
ear_t = 8;
// How far the ears stick out past the ring
ear_len = 12;
// Fillet radius where ears / mount meet the ring
fillet = 3;
// Width of the fit_test slice
fit_test_w = 10;

/* [Cable tie] */
// Tab with a zip-tie slot on the +X ear to anchor the monitor's power cord
cable_tie = true;
tie_tab = 7;
tie_slot = [2.2, 5];  // fits ties up to ~4.5 mm wide

/* [Clamp hardware] */
bolt_clear_d = 4.5;   // M4 clearance
bolt_head_d = 7.8;    // M4 socket head + clearance
bolt_head_depth = 4;
nut_af = 7.0;         // M4 nut across flats
nut_t = 3.4;          // M4 nut thickness + clearance

/* [Accessory mount] */
mount_type = "shoe"; // [shoe, quarter20, both]
// Width of the mount block (across the lens)
mount_w = 26;
// Minimum plastic between any mount feature and the bore
bore_skin = 2;

/* [Shoe slot (ISO 518)] */
// Fit tolerance added to the nominal 18 x 2 mm shoe foot
shoe_tol = 0.4;
shoe_foot_w = 18.0;
shoe_foot_t = 2.0;
// Width of the opening between the rails (foot neck must pass through)
shoe_open_w = 12.6;
// Thickness of the retaining rails over the channel
shoe_rail_t = 2.5;
// Depth of the channel along the lens axis; the rest is an end stop
shoe_depth = 18;

/* [1/4"-20 mount] */
quarter20_style = "insert"; // [insert, nut, tap]
// Heat-set insert hole: check your insert's datasheet
insert_hole_d = 8.0;
insert_len = 8.0;
// Captive 1/4"-20 hex nut (7/16" AF)
q_nut_af = 11.3;
q_nut_t = 6.0;
q_nut_cover = 3.0;    // plastic between mount face and the nut
q_clear_d = 6.8;      // 1/4" screw clearance
// Tap-drill hole for tapping 1/4"-20 directly into the plastic (#7 drill)
tap_d = 5.1;
tap_depth = 9;

/* [Hidden] */
$fn = 128;
eps = 0.01;

preset_d =
    lens_preset == "EF 24 f/2.8 IS USM"          ? 68.4 :
    lens_preset == "EF 24 f/1.4L II"             ? 93.5 :
    lens_preset == "EF 24-70 f/2.8L II"          ? 88.5 :
    lens_preset == "EF 70-200 f/2.8L IS II/III"  ? 88.8 :
    lens_preset == "EF 24-105 f/4L IS"           ? 83.5 :
    lens_preset == "RF 24-70 f/2.8L IS"          ? 88.5 :
    lens_preset == "RF 24-105 f/4L IS"           ? 83.5 :
    lens_preset == "EF 50 f/1.8 STM"             ? 69.2 :
    lens_d;

fit_test = part == "fit_test";
// Effective axial width
w = fit_test ? fit_test_w : ring_w;

inner_r = preset_d / 2 + liner_t;
outer_r = inner_r + wall;
bolt_x = outer_r + ear_len / 2;

has_shoe = !fit_test && (mount_type == "shoe" || mount_type == "both");
has_q20  = !fit_test && (mount_type == "quarter20" || mount_type == "both");
has_tie  = !fit_test && cable_tie;

shoe_ch_w = shoe_foot_w + shoe_tol;
shoe_ch_h = shoe_foot_t + shoe_tol;
shoe_stack = has_shoe ? shoe_rail_t + shoe_ch_h : 0;

// Depth the 1/4"-20 feature needs below the surface it starts from
q20_depth =
    !has_q20                     ? 2 :
    quarter20_style == "insert"  ? insert_len + 1 :
    quarter20_style == "nut"     ? q_nut_cover + q_nut_t + 1 :
                                   tap_depth;

// Top of the mount block: tall enough that nothing breaks into the bore
mount_top = max(outer_r + 3, inner_r + bore_skin + q20_depth + shoe_stack);
// Surface the 1/4"-20 feature starts from (shoe floor, or block top)
q20_face = mount_top - shoe_stack;
// Axial position of the 1/4"-20 feature (centred in the shoe channel if any)
q20_y = has_shoe ? -w / 2 + shoe_depth / 2 : 0;

assert(!has_shoe || w >= shoe_depth + 2,
       "ring_w must be at least shoe_depth + 2 to leave an end stop");
assert(!has_shoe || mount_w >= shoe_ch_w + 4,
       "mount_w too narrow for the shoe channel walls");
assert(clamp_gap < 2 * ear_t - 2, "clamp_gap is far too large");

// ---------- 2D profile (X across, Y here = Z in the part) ----------

module outline_2d() {
    // Fill concave corners between ring, ears and mount block
    offset(r = -fillet) offset(r = fillet) union() {
        circle(r = outer_r);
        // clamp ears
        for (s = [-1, 1])
            translate([s > 0 ? outer_r - wall / 2 : -(outer_r + ear_len), -ear_t])
                square([ear_len + wall / 2 + (s > 0 && has_tie ? tie_tab : 0), 2 * ear_t]);
        // mount block
        if (!fit_test)
            translate([-mount_w / 2, outer_r * 0.5])
                square([mount_w, mount_top - outer_r * 0.5]);
    }
}

module profile_2d() {
    difference() {
        outline_2d();
        circle(r = inner_r);
    }
}

// ---------- 3D features ----------

module clamp_bolts() {
    for (s = [-1, 1]) translate([s * bolt_x, 0, 0]) {
        cylinder(d = bolt_clear_d, h = 4 * ear_t, center = true);
        // socket head counterbore in the top ear
        translate([0, 0, ear_t - bolt_head_depth])
            cylinder(d = bolt_head_d, h = ear_t);
        // hex nut trap in the bottom ear
        translate([0, 0, -ear_t - eps])
            rotate([0, 0, 30]) cylinder(d = nut_af / cos(30), h = nut_t + eps, $fn = 6);
    }
}

module shoe_slot() {
    y0 = -w / 2 - 1;           // open at the -Y end
    len = shoe_depth + 1;
    ch_z = mount_top - shoe_rail_t - shoe_ch_h;
    // channel for the foot
    translate([-shoe_ch_w / 2, y0, ch_z]) cube([shoe_ch_w, len, shoe_ch_h]);
    // opening between the rails
    translate([-shoe_open_w / 2, y0, ch_z]) cube([shoe_open_w, len, shoe_stack + 1]);
    // lead-in chamfer on the open end of the rails
    translate([0, -w / 2, mount_top])
        rotate([-90, 0, 0])
            linear_extrude(height = 1.5, scale = [shoe_open_w / (shoe_open_w + 3), 1])
                square([shoe_open_w + 3, 2 * shoe_rail_t + 0.2], center = true);
}

module quarter20() {
    translate([0, q20_y, q20_face]) {
        if (quarter20_style == "insert") {
            translate([0, 0, -insert_len]) cylinder(d = insert_hole_d, h = insert_len + eps);
            // small lead-in so the insert starts straight
            translate([0, 0, -0.8]) cylinder(d1 = insert_hole_d, d2 = insert_hole_d + 1.2, h = 0.8 + eps);
        } else if (quarter20_style == "nut") {
            // screw clearance through the cover, nut pocket, and room for screw tip
            translate([0, 0, -q20_depth]) cylinder(d = q_clear_d, h = q20_depth + eps);
            // nut pocket with a slot to slide it in from the -Y face
            translate([0, 0, -q_nut_cover - q_nut_t]) {
                rotate([0, 0, 30]) cylinder(d = q_nut_af / cos(30), h = q_nut_t, $fn = 6);
                translate([-q_nut_af / 2, -w, 0]) cube([q_nut_af, w, q_nut_t]);
            }
        } else {
            translate([0, 0, -tap_depth]) cylinder(d = tap_d, h = tap_depth + eps);
        }
    }
}

module full_ring() {
    difference() {
        rotate([90, 0, 0]) linear_extrude(height = w, center = true) profile_2d();
        clamp_bolts();
        if (has_tie)
            translate([outer_r + ear_len + tie_tab / 2, 0, 0])
                cube([tie_slot[0], tie_slot[1], 4 * ear_t], center = true);
        if (has_shoe) shoe_slot();
        if (has_q20) quarter20();
    }
}

// ---------- Halves ----------
// Each half loses clamp_gap/2 at its split face and is shifted back to the
// split line, so the bolted-up bore is slightly undersized vertically and
// squeezes the liner.

big = 4 * (mount_top + ear_len);

module top_half() {
    translate([0, 0, -clamp_gap / 2]) intersection() {
        full_ring();
        translate([-big / 2, -big / 2, clamp_gap / 2]) cube(big);
    }
}

module bottom_half() {
    translate([0, 0, clamp_gap / 2]) intersection() {
        full_ring();
        translate([-big / 2, -big / 2, -big - clamp_gap / 2]) cube(big);
    }
}

module plate() {
    // both halves split-face down
    top_half();
    translate([0, -(w + 10), 0]) rotate([180, 0, 0]) bottom_half();
}

if (part == "assembly") {
    color("DimGray") top_half();
    color("SlateGray") translate([0, 0, -3]) bottom_half();
    // ghost of the lens
    %rotate([90, 0, 0]) cylinder(d = preset_d, h = w + 30, center = true);
} else if (part == "top") {
    top_half();
} else if (part == "bottom") {
    rotate([180, 0, 0]) bottom_half();
} else {
    plate();  // plate and fit_test
}

echo(str("Bore diameter (with liner) = ", 2 * inner_r, " mm, lens = ", preset_d, " mm"));
echo(str("Overall height above lens axis = ", mount_top, " mm"));
