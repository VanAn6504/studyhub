// A generated two-page PDF exercises the real PDF.js viewer and worker.
function fixturePdf() {
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 7 0 R >> >> /Contents 4 0 R >>',
    null,
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 7 0 R >> >> /Contents 6 0 R >>',
    null,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  ]
  for (const [index, text] of [
    [3, 'Row arranges children horizontally.'],
    [5, 'Column arranges children vertically.'],
  ]) {
    const stream = `BT /F1 12 Tf 20 260 Td (${text}) Tj ET\n`
    objects[index] = `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}endstream`
  }
  let pdf = '%PDF-1.4\n'
  const offsets = [0]
  objects.forEach((object, index) => {
    offsets.push(Buffer.byteLength(pdf))
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`
  })
  const xref = Buffer.byteLength(pdf)
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`
  pdf += offsets
    .slice(1)
    .map((offset) => `${String(offset).padStart(10, '0')} 00000 n \n`)
    .join('')
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`
  return Buffer.from(pdf)
}

module.exports = { fixturePdf }

// Varied page sizes, a real outline destination and an empty scan-like page.
module.exports.readerPdf = function readerPdf(count = 160) {
  const objects = ['','', '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
  const add = value => { objects.push(value); return objects.length }
  const pages = []
  for (let n = 1; n <= count; n++) {
    const stream = n === 3 ? '' : `BT /F1 12 Tf 20 250 Td (Reader page ${n}. Searchable normalization example.) Tj ET\n`
    const content = add(`<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}endstream`)
    pages.push(add(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${n % 4 === 0 ? '600 300' : '300 500'}] /Resources << /Font << /F1 3 0 R >> >> /Contents ${content} 0 R >>`))
  }
  const outline = add(''), entry = add(`<< /Title (Last chapter) /Parent ${outline} 0 R /Dest [${pages[count-1]} 0 R /Fit] >>`)
  objects[outline-1] = `<< /Type /Outlines /First ${entry} 0 R /Last ${entry} 0 R /Count 1 >>`
  objects[0] = `<< /Type /Catalog /Pages 2 0 R /Outlines ${outline} 0 R >>`
  objects[1] = `<< /Type /Pages /Kids [${pages.map(n => n+' 0 R').join(' ')}] /Count ${count} >>`
  let output = '%PDF-1.4\n'; const offsets = [0]
  objects.forEach((value,i) => { offsets.push(Buffer.byteLength(output)); output += `${i+1} 0 obj\n${value}\nendobj\n` })
  const xref = Buffer.byteLength(output)
  output += `xref\n0 ${objects.length+1}\n0000000000 65535 f \n`+offsets.slice(1).map(n=>String(n).padStart(10,'0')+' 00000 n \n').join('')+`trailer\n<< /Size ${objects.length+1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`
  return Buffer.from(output)
}
