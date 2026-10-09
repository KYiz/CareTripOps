export interface TravelImage {
  destination: string | null;
  attraction: string | null;
  image_url: string;
  source: string;
  alt_text: string;
  license: string;
  attribution: string;
  source_url: string;
  illustrative?: boolean;
}

export const travelImages: TravelImage[] = [
  { destination: 'Auckland', attraction: 'Auckland Harbour', image_url: '/images/auckland-harbour.webp', source: 'Wikimedia Commons', alt_text: 'Auckland skyline and harbour in New Zealand', license: 'CC BY-SA 4.0', attribution: 'WBPchur; converted to WebP', source_url: 'https://commons.wikimedia.org/wiki/File:Auckland_skyline_from_harbour.png' },
  { destination: 'Auckland', attraction: 'Sky Tower', image_url: '/images/auckland.webp', source: 'Wikimedia Commons', alt_text: 'Sky Tower among Auckland city buildings', license: 'Public domain', attribution: 'Entropy1963', source_url: 'https://commons.wikimedia.org/wiki/File:Auckland_skyline.jpg' },
  { destination: 'Queenstown', attraction: 'Lake Wakatipu', image_url: '/images/queenstown.webp', source: 'Wikimedia Commons', alt_text: 'Lake Wakatipu viewed from Queenstown', license: 'CC BY 4.0', attribution: 'Summ23; converted to WebP', source_url: 'https://commons.wikimedia.org/wiki/File:Lake_Wakatipu_NZ.jpg' },
  { destination: 'Queenstown', attraction: 'Skyline Queenstown', image_url: '/images/skyline-queenstown.webp', source: 'Wikimedia Commons', alt_text: 'Skyline Queenstown hillside and gondola area', license: 'CC BY 2.0', attribution: 'Gwydion M. Williams; converted to WebP', source_url: 'https://commons.wikimedia.org/wiki/File:Skyline_Queenstown_209.jpg' },
  { destination: 'Rotorua', attraction: 'Wai-O-Tapu', image_url: '/images/wai-o-tapu-palette.webp', source: 'Wikimedia Commons', alt_text: 'Artists Palette geothermal pools near Rotorua', license: 'CC BY 2.0', attribution: 'Vishal D. Makwana; converted to WebP', source_url: "https://commons.wikimedia.org/wiki/File:Artist%27s_Palette,_Wai_O_Tapu_Thermal_Wonderland.jpg" },
  { destination: 'Rotorua', attraction: 'Lake Rotorua', image_url: '/images/rotorua.webp', source: 'Wikimedia Commons', alt_text: 'Lake Rotorua in New Zealand', license: 'Public domain', attribution: 'Entropy1963', source_url: 'https://commons.wikimedia.org/wiki/File:Rotorua_Lake.jpg' },
  { destination: 'Wellington', attraction: 'Wellington Harbour', image_url: '/images/wellington.webp', source: 'Wikimedia Commons', alt_text: 'Wellington Harbour viewed from Te Ara Tupua', license: 'CC BY 4.0', attribution: 'Wainuiomartian; converted to WebP', source_url: 'https://commons.wikimedia.org/wiki/File:Wellington_Harbour_from_Te_Ara_Tupua.jpg' },
  { destination: 'Christchurch', attraction: 'Christchurch Botanic Gardens', image_url: '/images/christchurch.webp', source: 'Wikimedia Commons', alt_text: 'Christchurch Botanic Gardens in summer', license: 'CC BY 4.0', attribution: 'HeatherJoyMilne; converted to WebP', source_url: 'https://commons.wikimedia.org/wiki/File:The_Botanic_Gardens_in_Christchurch_New_Zealand.jpg' },
  { destination: 'Taupō', attraction: 'Lake Taupō', image_url: '/images/taupo.webp', source: 'Wikimedia Commons', alt_text: 'Lake Taupō in New Zealand', license: 'CC BY-SA 4.0', attribution: 'L3lzo; converted to WebP', source_url: 'https://commons.wikimedia.org/wiki/File:Lake_Taupo_North_Island_NZ.jpg' },
];

export const fallbackImage: TravelImage = {
  ...travelImages[2], destination: null, attraction: null,
  alt_text: 'Illustrative New Zealand landscape; destination photo unavailable', illustrative: true,
};

export function matchTravelImage(destination: string | null | undefined, attraction?: string | null): TravelImage {
  if (attraction) {
    const exact = travelImages.find(image => image.destination === destination && image.attraction === attraction);
    if (exact) return exact;
  }
  return travelImages.find(image => image.destination === destination) ?? fallbackImage;
}

export function matchAttractionImages(destination: string | null | undefined, attractions: string[]): TravelImage[] {
  return attractions.map(attraction => travelImages.find(image => image.destination === destination && image.attraction === attraction))
    .filter((image): image is TravelImage => Boolean(image));
}
