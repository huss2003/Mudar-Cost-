import * as pdfjsLib from 'pdfjs-dist';
import type { PDFDocumentProxy } from 'pdfjs-dist';

pdfjsLib.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjsLib.version}/pdf.worker.min.js`;

/**
 * Convert a PDF File into an array of PNG File objects (one per page).
 * Each page is rendered at 2× scale for crisp output.
 */
export async function convertPdfToImages(
  file: File,
  scale = 2
): Promise<File[]> {
  const arrayBuffer = await file.arrayBuffer();
  const pdf: PDFDocumentProxy = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;

  const pages: File[] = [];

  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i);
    const viewport = page.getViewport({ scale });

    const canvas = document.createElement('canvas');
    canvas.width = viewport.width;
    canvas.height = viewport.height;

    const ctx = canvas.getContext('2d');
    if (!ctx) {
      throw new Error('Failed to get 2D canvas context');
    }

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
        if (blob) {
          resolve(blob);
        } else {
          reject(new Error('Canvas toBlob returned null'));
        }
      },
      'image/png',
      1
    );
  });
}
