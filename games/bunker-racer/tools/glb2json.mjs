// Convert .glb files to self-contained glTF JSON (buffers as data URIs).
// Used for hosts that serve .json but not binary model types.
//   node tools/glb2json.mjs assets/*.glb --out <dir>
import fs from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);
const outIdx = args.indexOf('--out');
const outDir = outIdx >= 0 ? args[outIdx + 1] : 'assets';
const files = args.filter((a, i) => a !== '--out' && i !== outIdx + 1);
fs.mkdirSync(outDir, { recursive: true });
for (const file of files) {
  const buf = fs.readFileSync(file);
  if (buf.readUInt32LE(0) !== 0x46546c67) throw new Error(`${file} is not a GLB`);
  let off = 12, json = null, bin = null;
  while (off < buf.length) {
    const len = buf.readUInt32LE(off), type = buf.readUInt32LE(off + 4);
    const chunk = buf.subarray(off + 8, off + 8 + len);
    if (type === 0x4e4f534a) json = JSON.parse(chunk.toString('utf8'));
    else if (type === 0x004e4942) bin = chunk;
    off += 8 + len;
  }
  if (bin && json.buffers && json.buffers[0]) json.buffers[0].uri = `data:application/octet-stream;base64,${bin.toString('base64')}`;
  const out = path.join(outDir, path.basename(file, '.glb') + '.json');
  fs.writeFileSync(out, JSON.stringify(json));
  console.log(`${out}: ${(fs.statSync(out).size / 1024).toFixed(0)} KB`);
}
