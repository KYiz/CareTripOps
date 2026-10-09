import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';
import { fallbackImage, matchAttractionImages, matchTravelImage, travelImages } from '../src/data/travelImages.ts';

test('Auckland, Queenstown, and Rotorua resolve to distinct local photos', () => {
  const urls = ['Auckland', 'Queenstown', 'Rotorua'].map(destination => matchTravelImage(destination).image_url);
  assert.equal(new Set(urls).size, 3);
  assert.ok(urls.every(url => url.endsWith('.webp')));
});

test('attraction matching uses the destination and never borrows another place', () => {
  assert.equal(matchTravelImage('Queenstown', 'Skyline Queenstown').image_url, '/images/skyline-queenstown.webp');
  assert.equal(matchTravelImage('Queenstown', 'Unknown Falls').destination, 'Queenstown');
  assert.equal(matchAttractionImages('Queenstown', ['Unknown Falls']).length, 0);
});

test('an unknown destination uses a clearly illustrative fallback', () => {
  assert.equal(matchTravelImage('Unknown').image_url, fallbackImage.image_url);
  assert.equal(matchTravelImage('Unknown').illustrative, true);
});

test('every licensed photo has a real local WebP asset and source metadata', () => {
  for (const image of travelImages) {
    assert.ok(image.source_url.startsWith('https://commons.wikimedia.org/wiki/File:'));
    assert.ok(image.license && image.attribution && image.alt_text);
    const bytes = readFileSync(join('public', image.image_url));
    assert.equal(bytes.toString('ascii', 0, 4), 'RIFF');
    assert.equal(bytes.toString('ascii', 8, 12), 'WEBP');
  }
});
