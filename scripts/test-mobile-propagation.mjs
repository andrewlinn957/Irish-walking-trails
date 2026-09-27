import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const html = readFileSync(new URL("../dist/index.html", import.meta.url), "utf8");
const start = html.indexOf("    function p1812KnifeEdgeLoss(");
const end = html.indexOf("    function mobileSignalBand(", start);
assert(start >= 0 && end > start, "could not find the deployed propagation functions");
const context = {};
vm.runInNewContext(`${html.slice(start, end)}\nglobalThis.mobileModel = { p1812DeltaBullingtonDiffraction };`, context);
const climateStart = html.indexOf("    function mobileClimatologyAt(");
const climateEnd = html.indexOf("    function terrainPixelElevation(", climateStart);
assert(climateStart >= 0 && climateEnd > climateStart, "could not find the deployed climatology interpolator");
vm.runInNewContext(`${html.slice(climateStart, climateEnd)}\nglobalThis.mobileModel.mobileClimatologyAt = mobileClimatologyAt;`, context);
const diffraction = context.mobileModel.p1812DeltaBullingtonDiffraction;

const pointCount = 31;
const flatTerrain = () => Array(pointCount).fill(0);
const openCover = () => Array(pointCount).fill(0);

test("clear, short median path has negligible diffraction", () => {
  const loss = diffraction(flatTerrain(), openCover(), 1000, 900, 41);
  assert.ok(loss >= 0 && loss < 0.1, `unexpected diffraction loss ${loss}`);
});

test("an intervening ridge increases diffraction loss", () => {
  const ridge = flatTerrain();
  ridge[Math.floor(pointCount / 2)] = 50;
  const openPath = diffraction(flatTerrain(), openCover(), 5000, 900, 41);
  const obstructedPath = diffraction(ridge, openCover(), 5000, 900, 41);
  assert.ok(obstructedPath > openPath + 10, `${obstructedPath} dB was not above ${openPath} dB`);
});

test("forest or built clutter raises an otherwise flat profile", () => {
  const openPath = diffraction(flatTerrain(), openCover(), 5000, 900, 41);
  const clutteredPath = diffraction(flatTerrain(), Array(pointCount).fill(15), 5000, 900, 41);
  assert.ok(clutteredPath > openPath + 5, `${clutteredPath} dB was not above ${openPath} dB`);
});

test("the model is monotonic with distance and ridge frequency in these checks", () => {
  const ridge = flatTerrain();
  ridge[Math.floor(pointCount / 2)] = 50;
  const shortPath = diffraction(flatTerrain(), openCover(), 5000, 900, 41);
  const longPath = diffraction(flatTerrain(), openCover(), 40000, 900, 41);
  const lowBand = diffraction(ridge, openCover(), 5000, 700, 41);
  const highBand = diffraction(ridge, openCover(), 5000, 3500, 41);
  assert.ok(longPath > shortPath, `${longPath} dB was not above ${shortPath} dB`);
  assert.ok(highBand > lowBand, `${highBand} dB was not above ${lowBand} dB`);
});

test("the official Ireland refractivity grid interpolates exact grid points", () => {
  const climate = JSON.parse(readFileSync(new URL("../dist/data/mobile-climate.json", import.meta.url), "utf8"));
  const row = climate.latitudes.indexOf(54);
  const column = climate.longitudes.indexOf(354);
  const result = context.mobileModel.mobileClimatologyAt([-6, 54], climate);
  assert.equal(result.deltaN, climate.deltaN[row][column]);
  assert.equal(result.n0, climate.n0[row][column]);
  assert.ok(result.deltaN > 30 && result.deltaN < 60);
});
