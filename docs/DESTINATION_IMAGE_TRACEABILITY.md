# New Zealand Destination and Image Traceability

## Scope

The P0 destination vocabulary is maintained in `backend/app/skills/destinations.py`. It supports Auckland, Queenstown, Rotorua, Wellington, Christchurch, and Taupō with common English and Chinese aliases. The Requirements Worker stores the canonical destination, recognized attractions, pace, and `SUPPORTED` / `OUTSIDE_NZ` / `UNKNOWN` scope in the existing `requirements` table. A recognized foreign destination produces a persisted `DESTINATION_OUTSIDE_NZ` audit event and ends in `HUMAN_REVIEW` before supplier discovery. An unknown destination requests clarification. The synthetic A/C/B supplier fixture still serves only the fixed Auckland demonstration; other New Zealand destinations can be recognized and photographed but currently have no verified sample offer.

Photos are presentation data in the React SPA. `frontend/src/data/travelImages.ts` maps persisted requirements to local WebP assets; both desktop and phone import that same mapping. Photos do not enter Skills, evidence records, approval checks, or booking decisions. Unknown attractions use the destination photo. Unknown destinations or a failed image request use a New Zealand landscape explicitly labeled illustrative. A second image failure leaves a neutral placeholder and does not block planning.

## Image sources and licenses

All files below are local WebP conversions of real Wikimedia Commons photographs, resized to at most 1400 × 1050 pixels. The linked source pages contain the original and license terms. Attribution and license are also stored in the frontend metadata and displayed with the main photo.

| Local asset | Destination / attraction | Creator | License | Original |
|---|---|---|---|---|
| `auckland-harbour.webp` | Auckland / Auckland Harbour | WBPchur | CC BY-SA 4.0 | [Source](https://commons.wikimedia.org/wiki/File:Auckland_skyline_from_harbour.png) |
| `auckland.webp` | Auckland / Sky Tower | Entropy1963 | Public domain | [Source](https://commons.wikimedia.org/wiki/File:Auckland_skyline.jpg) |
| `queenstown.webp` | Queenstown / Lake Wakatipu | Summ23 | CC BY 4.0 | [Source](https://commons.wikimedia.org/wiki/File:Lake_Wakatipu_NZ.jpg) |
| `skyline-queenstown.webp` | Queenstown / Skyline Queenstown | Gwydion M. Williams | CC BY 2.0 | [Source](https://commons.wikimedia.org/wiki/File:Skyline_Queenstown_209.jpg) |
| `wai-o-tapu-palette.webp` | Rotorua / Wai-O-Tapu | Vishal D. Makwana | CC BY 2.0 | [Source](https://commons.wikimedia.org/wiki/File:Artist%27s_Palette,_Wai_O_Tapu_Thermal_Wonderland.jpg) |
| `rotorua.webp` | Rotorua / Lake Rotorua | Entropy1963 | Public domain | [Source](https://commons.wikimedia.org/wiki/File:Rotorua_Lake.jpg) |
| `wellington.webp` | Wellington / Wellington Harbour | Wainuiomartian | CC BY 4.0 | [Source](https://commons.wikimedia.org/wiki/File:Wellington_Harbour_from_Te_Ara_Tupua.jpg) |
| `christchurch.webp` | Christchurch / Botanic Gardens | HeatherJoyMilne | CC BY 4.0 | [Source](https://commons.wikimedia.org/wiki/File:The_Botanic_Gardens_in_Christchurch_New_Zealand.jpg) |
| `taupo.webp` | Taupō / Lake Taupō | L3lzo | CC BY-SA 4.0 | [Source](https://commons.wikimedia.org/wiki/File:Lake_Taupo_North_Island_NZ.jpg) |

The local asset builder is `frontend/scripts/build_photo_library.py`. Runtime use needs no image API, API key, image generation, or extra service. P1 online search and caching are not implemented.

## Four browser entry points and daily outline

The single React SPA serves `/` (brand entry), `/dashboard` (operations), `/mobile` (traveler phone view), and `/demo` (both views) on port 8080. All four paths use the same `/api/*` client, case ID, FastAPI service, and PostgreSQL database. Nginx serves `index.html` for direct navigation and refresh. The web image copies `frontend/public` before the Vite build, so the local WebP library is included in the deployed assets.

`GET /api/cases/{case_id}` derives an `ILLUSTRATIVE_DRAFT` daily outline from the persisted destination, duration, and mentioned attractions. It contains no unverified supplier, schedule, transport, price, or booking claim. The phone view maps each day to a local destination or attraction photograph and labels the outline as an unbooked draft. The separate verified offer and approval sections continue to depend on evidence PASS and a persisted pending approval. The outline is presentation-only and adds no database table, LLM call, worker, or image service.

## V3.2 design alignment

| Design source | Existing implementation | New destination and image extension | Validation |
|---|---|---|---|
| System Architecture | One SPA, FastAPI, LangGraph, PostgreSQL, three Compose services | Static photo assets in the existing web service | Source review; deployment pending |
| Workflow | Requirements → discovery → evidence → approval → booking | Scope gate at Requirements; photos run only in React after API read | Pure Skill tests passed; API integration pending |
| ERD | Eight business tables and Alembic | Three columns on `requirements`, no ninth table | Alembic head recognized; migration execution pending |
| Frontend Interaction | One case ID and typed REST client | Both views consume the same requirements and image mapping | Type check and photo tests passed; browser pending |
| API Sequence | Case read and existing approval routes | Case read includes scope, attractions, pace | Static review; API contract test pending |
| Web Page Flow | Intake, requirements, offers, evidence, audit | Destination hero, attraction tiles, offer photos | Build passed; browser pending |
| Mobile Page Flow | Final PASS offer and existing approval endpoint | Large destination photo and simpler copy | Build passed; browser pending |

The V3.2 package is in `CareTrip_Final_Review_Package/`, not a directory with a `_V3_2` suffix. Its final review remains the primary business specification; the current user request adds the New Zealand presentation and scope requirements. The three package reference images guided hierarchy and visual tone only. The historical architecture image does not authorize extra agents, services, or databases.
