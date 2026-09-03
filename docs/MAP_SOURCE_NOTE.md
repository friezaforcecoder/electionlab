# Geographic map implementation note — 0.10

The U.S. election map geometry was created for ElectionLab by the project owner with ChatGPT assistance for ElectionLab 0.3.5. The generated source SVG remains bundled as `electionlab/data/us_map_source.svg`, with parsed geometry retained in `us_map_paths.json` for provenance/testing.

## 0.10 runtime change
Earlier builds converted the detailed SVG paths into Qt `QPainterPath` objects at runtime. Even after caching and raster hit-testing, Windows could spend tens of seconds transforming, stroking, or painting some of the extremely detailed paths.

0.10 therefore moved that geometry work to build time. Those original 0.10
raster tiles are superseded by the 0.11.1 index-raster compositor and are not
included in the public source tree.

At runtime ElectionLab only composites ordinary pixmaps and samples one hit-map pixel for mouse interaction. The detailed SVG remains the authoritative source asset but is no longer used for normal live rendering.

This architecture keeps:
- actual geographic state shapes,
- dynamic state coloring,
- state labels/EV labels where space permits,
- hover and click interaction,
- tiny-state click assistance,
- local/offline rendering,
- no WebEngine/browser dependency.

## 0.11 visual compositor repair

The fast raster hit map remains. The visible map no longer scales each cropped state mask independently. ElectionLab first composites all state masks and the outline at the shared 1028×746 source resolution and then scales that completed image once. This removes visible seams/offsets introduced by per-state scaling while keeping single-pixel state hit testing.


## 0.11.1 canonical compositor

The 0.11 compositor still relied on cropped state-mask tiles. Even when those tiles were composed at source resolution, crop-edge antialiasing and bbox differences could leave visible seams or clipped/drifting shapes. 0.11.1 removes that runtime representation.

Build assets now include `map_raster_v2/state_indexed.bin`: one byte per map pixel, where 0 is background and 1-51 identify a jurisdiction. The file is generated directly from each original SVG path on the complete source viewBox. Runtime recoloring changes the QImage color table rather than reconstructing geometry. `map_raster_v2/outline.png` is also rendered once from all SVG paths on that same full canvas.

The index raster is simultaneously the click/hit map, so displayed and interactive geography use the same coordinate system.
