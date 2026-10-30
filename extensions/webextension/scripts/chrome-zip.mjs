// Dependency-free, reproducible Chrome upload ZIP encoder (opener-0597).
// Exact archive allowlist deliberately excludes Firefox, source and secrets.
export const CHROME_PACKAGE_FILES = Object.freeze([
  "manifest.json", "background.js", "popup.html", "popup.css",
  "icons/icon-16.png", "icons/icon-32.png",
  "icons/icon-48.png", "icons/icon-128.png"
]);

function crc32(data) {
  let crc = 0xffffffff;
  for (const byte of data) {
    crc ^= byte;
    for (let i = 0; i < 8; i++) {
      crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

/** Encode only approved files as a deterministic ZIP STORE archive. */
export function encodeChromeZip(entries) {
  if (!Array.isArray(entries) || entries.length !== CHROME_PACKAGE_FILES.length) {
    throw new Error("Chrome ZIP must contain exactly eight approved files");
  }
  const localParts = [];
  const centralParts = [];
  let offset = 0;
  let centralLength = 0;
  let totalSize = 0;
  for (let i = 0; i < entries.length; i++) {
    const { name, bytes } = entries[i] ?? {};
    if (name !== CHROME_PACKAGE_FILES[i] || !Buffer.isBuffer(bytes) ||
        bytes.length === 0 || bytes.length > 2 * 1024 * 1024) {
      throw new Error("Unapproved or oversized Chrome ZIP entry");
    }
    totalSize += bytes.length;
    if (totalSize > 8 * 1024 * 1024) {
      throw new Error("Chrome ZIP exceeds maximum size");
    }
    const filename = Buffer.from(name, "utf8");
    const digest = crc32(bytes);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0x21, 12); // fixed DOS date: 1980-01-01
    local.writeUInt32LE(digest, 14);
    local.writeUInt32LE(bytes.length, 18);
    local.writeUInt32LE(bytes.length, 22);
    local.writeUInt16LE(filename.length, 26);
    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt16LE(0x21, 14);
    central.writeUInt32LE(digest, 16);
    central.writeUInt32LE(bytes.length, 20);
    central.writeUInt32LE(bytes.length, 24);
    central.writeUInt16LE(filename.length, 28);
    central.writeUInt32LE(offset, 42);
    localParts.push(local, filename, bytes);
    centralParts.push(central, filename);
    offset += local.length + filename.length + bytes.length;
    centralLength += central.length + filename.length;
  }
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(entries.length, 8);
  end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(centralLength, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...localParts, ...centralParts, end],
    offset + centralLength + end.length);
}
