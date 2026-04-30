# Phase 0 — Data Exploration Checklist

**Goal**: Build calibrated intuition about what's actually in your starting region's data before writing any code. No deliverable except your own informed sense of what you're working with.

**Total time**: 3-4 hours, can be split across 2-3 sessions.

**Mindset**: You are not building. You are not measuring. You are looking. If you find yourself reaching for code, stop and just keep looking.

---

## Part 1 — Setup (30-45 min)

### Install QGIS
- [x] Go to https://qgis.org/download/
- [x] Download the **Long Term Release** (LTR) installer for Windows — more stable than Latest Release
- [x] Run the installer with default options
- [x] Launch QGIS once to confirm it opens (it'll be slow on first launch — normal)
- [x] Close it; you'll reopen with data loaded

### Create a project folder
- [x] Make a folder somewhere obvious like `C:\Projects\fishing-tool\phase-0-data\`
- [x] Inside it, create subfolders: `ohn\`, `ara\`, `fish-stocking\`, `notes\`
- [x] This is where downloads go and where your QGIS project will live

### Set your working bounding box
- [x] Open Google Maps, find Scarborough (Meadowvale & Ellesmere area)
- [x] Mentally define a starting box: roughly **Lake Simcoe to the north, Pickering to the east, Brampton to the west, Lake Ontario to the south**. This is bigger than just FMZ 16 — intentionally — so you can see what's just beyond your starting region too.
- [x] Note the approximate corner coordinates (you can right-click in Google Maps to copy lat/lng). Save them in `notes\bounding_box.txt` for reference during downloads.

---

## Part 2 — Download datasets (45-60 min)

You're getting three datasets. The Ontario GeoHub interface lets you draw a bounding box and download just that area — use it. Don't download all of Ontario; the files are huge and you don't need them.

### Dataset 1: Ontario Hydro Network — Waterbody (the spine)

- [x] Go to https://geohub.lio.gov.on.ca/datasets/mnrf::ontario-hydro-network-ohn-waterbody
- [x] Click **Download** (top right area)
- [x] Choose **Shapefile** format (most universally compatible with QGIS)
- [x] Use the filter/clip option to restrict to your bounding box if available; otherwise download the smallest pre-clipped tile that covers your area
- [x] Save to `ohn\` folder, unzip if needed
- [ ] Note: file should be a few hundred MB at most for your area; if it's multiple GB you grabbed the whole province by accident — try again

### Dataset 2: Aquatic Resource Area Survey Point (the fish observations)

- [x] Go to https://geohub.lio.gov.on.ca/datasets/lio::aquatic-resource-area-survey-point
- [x] Download as Shapefile, clipped to your area
- [x] Save to `ara\` folder, unzip

### Dataset 3: Fish Stocking Data for Recreational Purposes (recent stocking)

- [x] Go to https://geohub.lio.gov.on.ca/datasets/mnrf::fish-stocking-data-for-recreational-purposes
- [x] Download as Shapefile
- [x] Save to `fish-stocking\` folder, unzip

### Sanity check
- [x] You should have three folders, each containing a `.shp` file plus several supporting files (`.shx`, `.dbf`, `.prj`, etc.). Don't delete the supporting files — shapefiles need them.

---

## Part 3 — Load data into QGIS (15-30 min)

### Create a project
- [x] Open QGIS
- [x] **Project → New**
- [x] **Project → Save As** → save to `C:\Projects\fishing-tool\phase-0-data\fmz16_exploration.qgz`

### Add a basemap so you have geographic context
- [x] In the Browser panel (left side), find **XYZ Tiles**
- [x] Right-click → **New Connection**
- [x] Name: `OpenStreetMap`, URL: `https://tile.openstreetmap.org/{z}/{x}/{y}.png`
- [x] Click OK, then double-click the new OpenStreetMap entry to add it to the map
- [x] You should now see a world map. Zoom into Scarborough.

### Load the OHN waterbody layer
- [x] **Layer → Add Layer → Add Vector Layer**
- [x] Browse to your `ohn\` folder, select the `.shp` file
- [x] Click Add, then Close
- [x] Layer appears in the map. Right-click the layer → **Zoom to Layer** to fit it on screen.
- [x] **Spend 30 seconds just looking.** You're seeing every mapped water body in your area.

### Load the ARA survey point layer
- [x] Same process: Layer → Add Layer → Add Vector Layer
- [x] Pick the `.shp` from `ara\`
- [x] These will appear as points overlaid on the water bodies

### Load the fish stocking layer
- [x] Same process for the file in `fish-stocking\`

### Style the layers so you can actually see them
- [x] Right-click the OHN waterbody layer → **Properties → Symbology**
- [x] Set fill color to something pale blue with ~50% opacity so the basemap shows through
- [x] Right-click the ARA layer → Properties → Symbology
- [x] Use a small bright color (e.g., bright orange) so points are visible
- [x] Right-click the fish stocking layer → make these a different color (e.g., bright green)
- [x] Save the project (**Ctrl+S**)

---

## Part 4 — Look at the data (60-90 min)

This is the actual work. Open `notes\observations.md` in any text editor and write things down as you notice them. The notes are the deliverable for Phase 0.

### Pass 1: Big picture (15 min)
- [x] Zoom out so the whole bounding box fits on screen
- [x] Just look. Don't click anything yet.
- [x] **Write down**: What's your immediate gut reaction? Lots of water? Sparse? Where is it concentrated?
- [x] Identify obvious clusters: Lake Simcoe, the Rouge system, Oak Ridges Moraine ponds, conservation areas

Toronto / Scarborough is bordered by Lake Ontario, however within Scarborough and Toronto as a whole, there isn't much water. Most of the water comes from Lake Ontario that breaks into Highland creek, Rouge River, and Frenchmans bay (this area is probably the most concentrated). There are isolated bodies of water within Toronto/ Scarborugh but not that many. There are also the major water bodies to the north and east like Scugog, Rice Lake, Kawartha, and Simcoe, each having smaller rivers branch off, maybe it would be worth while following those smaller rivers, same with highland creek and rouge. I still want to explore those isolated smaller bodies of water in toronto.

### Pass 2: Density and naming (20 min)
- [x] Pick a 10x10 km area you'd be willing to drive to (within ~45 min of home)
- [x] Zoom in tight on it
- [x] Click individual water bodies. The attribute popup shows you the OHN attributes including the name field.
- [x] **Count roughly**: How many water bodies in this area? How many have actual names vs. NULL/blank?
- [x] **Write down** the ratio. This is your first real data point about the "hidden gem" hypothesis. If 80% of water bodies are unnamed, the unnamed-as-hiddenness signal will work. If 95% are named, the signal is too rare to use.

It's hard to count the total water bodies in this as there is alot of are to cover because i'm looking at a 1 hour drive radius, but a rough estimate based on what i am seeing is that 80% of the water bodies I am seeing are unnamed, while there are 20% named like the major ones: Highland Creek, Rouge River, ect. But yes most have no Official name according to OHN.

### Pass 3: Where are the surveys? (15 min)
- [x] Zoom out to see ARA points across the whole region
- [x] **Notice**: Are points clustered on big-name lakes only? Are they spread evenly? Are there entire regions with zero points?
- [x] Click a few ARA points. The attribute popup shows survey type, date, species observed. Read a few.
- [x] **Write down**: How recent are most surveys? What species show up most? Which areas have zero coverage?
- [x] This tells you where your fish-prediction layer will be **inferring** vs. **looking up**.

The ARA points are mostly on the big name lakes, but there are some on unnamed bodies of water. There aren't any regions with zero points but there are regions with less. A Lot of these isolated bodies of water hold smaller species like minows, but there are some hot spots that have bass, bullheads, pike, and good catch fishes, especially off of rouge river. These points are from 2022 t0 2025. The aim are the bigger fish in the end.

### Pass 4: Find candidate hidden gems (20 min)
- [x] Zoom into areas that match these criteria, by eye:
  - Has unnamed small water bodies
  - Has named lakes nearby (potential source for connectivity inference)
  - Is near roads/trails (so accessible)
  - Is on what looks like park or conservation land (check basemap labels)
- [x] **Pick 3-5 specific candidate ponds**. Note their approximate coordinates.
- [x] For each: do they have any ARA survey point within ~2km? Any fish stocking record within the same drainage?
- [x] **Write these down**. These are the spots you'll mentally validate your tool against later. If the tool eventually surfaces these, that's a sanity-check pass. If it ranks them low, something's wrong.

There are smaller bodies of water but they don't have lakes that connect (isolated) and some are accessible and some are not. I noticed that most the fish stocking is near kawartha, maybe it would be worth it to expand our search to up there are well.

### Pass 5: Reality check on your starting region (10 min)
- [x] Honestly assess: does FMZ 16 (your home region) actually have enough hidden-gem candidates?
- [x] Or are most water bodies obviously roadside, named, on private land, or otherwise non-hidden?
- [x] **Write down** your honest read: stay with FMZ 16, or shift the starting box slightly north (toward Kawarthas / Oak Ridges) before Phase 1?
- [x] This is the **single most important output of Phase 0**. The starting region decision determines whether your first build runs against an interesting dataset.

---

There definantly are some potential hidden gems in scarborough that will be tough to find, however I think there will be a lot more up north near kawartha becuase that area has the most ARA points and Fish stocking points. I want to explore both areas. For the FMZ16 hidden gems I will definely need Multi Agents anaylzing the data and maps to help me find potenial candidates. 

## Part 5 — Reflection notes (15 min)

In `notes\phase_0_summary.md`, answer these in plain English. Doesn't have to be polished — these are notes for your future self.

- [x] **Density**: Roughly how many water bodies exist in your candidate driving range?
- [x] **Naming ratio**: What % are unnamed?
- [x] **Survey coverage**: What % of water bodies have any survey data within reasonable connectivity distance?
- [x] **Top 3-5 manual candidates**: Rough coordinates, why you flagged each
- [x] **Region decision**: FMZ 16 confirmed, or shift?
- [x] **Surprises**: Anything you didn't expect when looking at the data?
- [x] **Concerns**: What looks like it might be a problem for the tool?
- [x] **Excitement**: What looks more promising than you expected?

---

There are alot of water bodies in my cadidate driving range.
80% are unnamed.
60%.
I don't have cooridnates as of right now.
FMZ16 + kawartha lakes, scugog, rice lake, simcoe area.
I didn't expect there to be so much activity in my area, but most of it is small fish like minows that I want to avoid.
Identifying gems is still looking hard. I don't want to the tool to outright ignore big name areas like rouge because there are areas within the rougue that might not be easily accessible but can still be travelled to and be a gem.
This whole thing is looks promising if executed correctly.

## Done criteria

You're done with Phase 0 when:
- [x] You can describe out loud what's in the data for your region in 2-3 sentences
- [x] You've decided on FMZ 16 vs. a shift
- [x] You have 3-5 manual candidate ponds noted as a sanity-check set
- [x] You have a written summary in `notes\phase_0_summary.md`

You do **not** need to:
- Write any code
- Set up Postgres
- Install Python libraries
- Decide on schema
- Solve any problem you noticed

If you noticed problems, that's a Phase 0 success — write them down and bring them to the next conversation.

---

## If you get stuck

**Can't find the download button on GeoHub**: Some datasets only expose ESRI REST endpoints, not direct downloads. If that's the case, use the "Open in ArcGIS Online" link, then look for download options there. If still stuck, the OHN data is also mirrored on data.ontario.ca with direct download links.

**QGIS won't load the shapefile**: Most likely you're missing one of the supporting files (`.shx`, `.dbf`, `.prj`). Re-extract from the original zip, make sure all files are in the same folder.

**Data appears in the wrong location** (e.g., off the coast of Africa): Coordinate system mismatch. Right-click the layer → Properties → Source → set CRS. Most Ontario data is EPSG:3161 (Ontario MNR Lambert) or EPSG:4326 (WGS84). Try setting it to one of these.

**Files are huge and QGIS is slow**: You probably grabbed all of Ontario instead of your bounding box. Re-download with proper clipping, or use QGIS's Vector → Geoprocessing Tools → Clip to clip the layer to your area of interest.

---

## After Phase 0

Bring your `phase_0_summary.md` notes back to the next conversation. We'll do the gap-analysis pass *informed by what you actually saw*, then move into Phase 1.
