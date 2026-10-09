"""Download attributed Wikimedia Commons source photos and create local WebP assets."""

import hashlib
from io import BytesIO
from pathlib import Path
from time import sleep
from urllib.parse import quote
from urllib.request import Request, urlopen

from PIL import Image, ImageOps


PHOTOS = {
    "auckland": "Auckland_skyline.jpg",
    "auckland-harbour": "Auckland_skyline_from_harbour.png",
    "queenstown": "Lake_Wakatipu_NZ.jpg",
    "skyline-queenstown": "Skyline_Queenstown_209.jpg",
    "rotorua": "Rotorua_Lake.jpg",
    "wai-o-tapu-palette": "Artist's_Palette,_Wai_O_Tapu_Thermal_Wonderland.jpg",
    "wellington": "Wellington_Harbour_from_Te_Ara_Tupua.jpg",
    "christchurch": "The_Botanic_Gardens_in_Christchurch_New_Zealand.jpg",
    "taupo": "Lake_Taupo_North_Island_NZ.jpg",
}


def main() -> None:
    output = Path(__file__).resolve().parents[1] / "public" / "images"
    output.mkdir(parents=True, exist_ok=True)
    for slug, filename in PHOTOS.items():
        target = output / f"{slug}.webp"
        if target.exists():
            print(f"{slug}: already present")
            continue
        digest = hashlib.md5(filename.encode()).hexdigest()
        url = f"https://upload.wikimedia.org/wikipedia/commons/{digest[0]}/{digest[:2]}/{quote(filename)}"
        request = Request(url, headers={"User-Agent": "CareTripOpsDemo/1.0 (local educational demo)"})
        with urlopen(request, timeout=30) as response:
            source = response.read()
        with Image.open(BytesIO(source)) as original:
            picture = ImageOps.exif_transpose(original).convert("RGB")
            picture.thumbnail((1400, 1050))
            picture.save(target, format="WEBP", quality=78, method=6)
        print(f"{slug}: {target.stat().st_size} bytes")
        sleep(3)


if __name__ == "__main__":
    main()
