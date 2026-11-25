/**
 * Riduzione delle foto sul dispositivo, prima della cifratura e dell'invio (decisione del 25/11/2026):
 * lato lungo al massimo 1600 px, JPEG all'80% (circa 0,3-0,5 MB invece dei 3-6 MB dell'originale).
 * Ridisegnare l'immagine su una tela elimina anche i dati EXIF (posizione GPS, modello del telefono):
 * la posizione dell'evento è già registrata a parte.
 */
export interface PreparedPhoto {
  bytes: Uint8Array;
  width: number;
  height: number;
}

/** Tentativi in ordine: se la foto resta oltre la soglia (scene molto dettagliate) si riduce ancora. */
const STEPS: readonly (readonly [maxSide: number, quality: number])[] = [
  [1600, 0.8],
  [1400, 0.72],
  [1200, 0.65],
];
const TARGET_BYTES = 900 * 1024;

interface Decoded { source: CanvasImageSource; width: number; height: number; close: () => void }

async function decode(file: Blob): Promise<Decoded> {
  if (typeof createImageBitmap === 'function') {
    try {
      const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' });
      return { source: bmp, width: bmp.width, height: bmp.height, close: () => bmp.close() };
    } catch {
      /* formato non gestito da createImageBitmap: si prova con <img> */
    }
  }
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    return { source: img, width: img.naturalWidth, height: img.naturalHeight, close: () => undefined };
  } finally {
    URL.revokeObjectURL(url);
  }
}

export async function preparePhoto(file: Blob): Promise<PreparedPhoto> {
  let decoded: Decoded;
  try {
    decoded = await decode(file);
  } catch {
    throw new Error('photo_unreadable');
  }
  try {
    if (!decoded.width || !decoded.height) throw new Error('photo_unreadable');
    let last: PreparedPhoto | null = null;
    for (const [maxSide, quality] of STEPS) {
      const scale = Math.min(1, maxSide / Math.max(decoded.width, decoded.height));
      const width = Math.max(1, Math.round(decoded.width * scale));
      const height = Math.max(1, Math.round(decoded.height * scale));
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error('photo_unreadable');
      ctx.fillStyle = '#fff'; // eventuali trasparenze (PNG) su fondo bianco
      ctx.fillRect(0, 0, width, height);
      ctx.drawImage(decoded.source, 0, 0, width, height);
      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality));
      if (!blob) throw new Error('photo_unreadable');
      last = { bytes: new Uint8Array(await blob.arrayBuffer()), width, height };
      if (blob.size <= TARGET_BYTES) break;
    }
    return last!;
  } finally {
    decoded.close();
  }
}
