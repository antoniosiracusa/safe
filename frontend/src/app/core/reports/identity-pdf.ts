/**
 * Documento completo: scrive nel PDF i dati identificativi decifrati, sul dispositivo dell'utente.
 *
 * Il server prepara il rapporto con campi modulo vuoti di nome `pii__<id persona>__<campo>` (non conosce
 * i dati). Qui i campi servono solo a sapere dove scrivere: il testo viene disegnato nella loro posizione
 * con lo stesso carattere del rapporto, poi i campi vengono rimossi, così il file risulta un PDF normale.
 */
const FIELD_NAME = /^pii__([0-9a-f-]{36})__([a-z_]+)$/;
const FONT_URL = 'fonts/DejaVuSans.ttf';
const FONT_SIZE = 8.5; // come il corpo del rapporto
const MIN_FONT_SIZE = 5.5;

export type Identities = ReadonlyMap<string, Readonly<Record<string, string>>>;

function clean(value: string): string {
  // i campi sono a riga singola: a capo e tabulazioni diventano spazi
  return value.replace(/\s+/g, ' ').trim();
}

export async function fillIdentityFields(pdf: ArrayBuffer, identities: Identities): Promise<Uint8Array> {
  const [{ PDFDocument, PDFName, rgb }, fontkit, fontBytes] = await Promise.all([
    import('pdf-lib'),
    import('@pdf-lib/fontkit').then((m) => m.default),
    fetch(FONT_URL).then((r) => {
      if (!r.ok) throw new Error('font_unavailable');
      return r.arrayBuffer();
    }),
  ]);
  const doc = await PDFDocument.load(pdf);
  doc.registerFontkit(fontkit);
  const font = await doc.embedFont(fontBytes, { subset: true });
  const form = doc.getForm();

  for (const field of form.getFields()) {
    const match = FIELD_NAME.exec(field.getName());
    const text = match ? clean(identities.get(match[1])?.[match[2]] ?? '') : '';
    for (const widget of field.acroField.getWidgets()) {
      const ref = doc.context.getObjectRef(widget.dict);
      const page = ref ? doc.findPageForAnnotationRef(ref) : undefined;
      if (page && text) {
        const rect = widget.getRectangle();
        const width = Math.abs(rect.width);
        const height = Math.abs(rect.height);
        const x = Math.min(rect.x, rect.x + rect.width);
        const y = Math.min(rect.y, rect.y + rect.height);
        // se il testo non entra si riduce il carattere; se ancora non entra si tronca con i puntini
        let size = FONT_SIZE;
        while (size > MIN_FONT_SIZE && font.widthOfTextAtSize(text, size) > width) size -= 0.25;
        let shown = text;
        while (shown.length > 1 && font.widthOfTextAtSize(shown, size) > width) shown = `${shown.slice(0, -2).trimEnd()}…`;
        page.drawText(shown, { x, y: y + (height - size) / 2 + size * 0.06, size, font, color: rgb(0.07, 0.07, 0.07) });
      }
      // il campo ha fatto il suo lavoro (indicare la posizione): via dalla pagina e dal documento.
      // Non si usa form.removeField: richiede un aspetto già disegnato, che questi campi vuoti non hanno.
      if (ref) {
        page?.node.removeAnnot(ref);
        doc.context.delete(ref);
      }
    }
    doc.context.delete(field.ref);
  }
  form.acroForm.dict.set(PDFName.of('Fields'), doc.context.obj([]));
  doc.catalog.delete(PDFName.of('AcroForm'));
  return doc.save({ updateFieldAppearances: false });
}
