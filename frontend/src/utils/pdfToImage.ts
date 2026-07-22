/**
 * PDF → PNG conversion using pdfjs-dist.
 * Runs on main thread (no web worker) to avoid CDN/CORS issues.
 */
let pdfjsLib: typeof import('pdfjs-dist') | null = null;

async function getPdfLib() {
  if (!pdfjsLib) {
    pdfjsLib = await import('pdfjs-dist');
    // Use locally bundled worker (copied to public/) to avoid CDN/CORS issues
    pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
      '/pdf.worker.min.mjs',
      import.meta.url
    ).href;
  }
  return pdfjsLib;
}

/**
 * Convert a PDF File into an array of PNG File objects (one per page).
 * Each page is rendered at 2× scale for crisp output.
 */
export async function convertPdfToImages(
  file: File,
  scale = 2
): Promise<File[]> {
  const lib = await getPdfLib();
  const arrayBuffer = await file.arrayBuffer();
  const pdf = await lib.getDocument({ data: arrayBuffer, useSystemFonts: true }).promise;

  const pages: File[] = [];

  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i);
    const viewport = page.getViewport({ scale });

    const canvas = document.createElement('canvas');
    canvas.width = viewport.width;
    canvas.height = viewport.height;

    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('Failed to get 2D canvas context');

    await page.render({ canvas, canvasContext: ctx, viewport }).promise;

    const blob = await canvasToBlob(canvas);
    const pngFile = new File([blob], `page_${i}.png`, { type: 'image/png' });
    pages.push(pngFile);
  }

  return pages;
}

/** Convert an HTMLCanvasElement to a Blob using a Promise wrapper. */
function canvasToBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob) resolve(blob);
        else reject(new Error('Canvas toBlob returned null'));
      },
      'image/png',
      1
    );
  });
}
