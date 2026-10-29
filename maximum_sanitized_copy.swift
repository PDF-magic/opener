import CoreGraphics
import Foundation

// opener-0313: optional, lossy visual-only PDF conversion. The input is
// immutable PDF bytes on stdin, not a document path. Output is a *new* PDF
// containing page raster images only. No source PDF dictionaries are copied.
private let maxInputBytes = 16 * 1024 * 1024
private let maxOutputBytes = 32 * 1024 * 1024
private let maxPages = 16
private let maxSidePixels = 2048
private let maxTotalPixels = 24_000_000

private func convert(_ data: Data) -> Data? {
    guard !data.isEmpty, data.count <= maxInputBytes,
          let provider = CGDataProvider(data: data as CFData),
          let document = CGPDFDocument(provider),
          !document.isEncrypted,
          (1...maxPages).contains(document.numberOfPages),
          let outputData = CFDataCreateMutable(nil, 0),
          let consumer = CGDataConsumer(data: outputData),
          let output = CGContext(consumer: consumer, mediaBox: nil, nil) else {
        return nil
    }

    var usedPixels = 0
    for index in 1...document.numberOfPages {
        guard let page = document.page(at: index) else {
            output.closePDF()
            return nil
        }
        let rotation = ((page.rotationAngle % 360) + 360) % 360
        guard [0, 90, 180, 270].contains(rotation) else {
            output.closePDF()
            return nil
        }
        let media = page.getBoxRect(.mediaBox)
        let crop = page.getBoxRect(.cropBox)
        guard media.origin.x.isFinite, media.origin.y.isFinite,
              media.width.isFinite, media.height.isFinite,
              (1.0...1440.0).contains(media.width),
              (1.0...1440.0).contains(media.height),
              crop == media else {
            output.closePDF()
            return nil
        }
        let scale = min(2.0, CGFloat(maxSidePixels) / max(media.width, media.height))
        let width = Int(ceil(media.width * scale))
        let height = Int(ceil(media.height * scale))
        guard width > 0, height > 0,
              width <= maxSidePixels, height <= maxSidePixels,
              width * height <= maxTotalPixels - usedPixels else {
            output.closePDF()
            return nil
        }
        usedPixels += width * height
        guard let bitmap = CGContext(
            data: nil, width: width, height: height,
            bitsPerComponent: 8, bytesPerRow: 0,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
        ) else {
            output.closePDF()
            return nil
        }
        bitmap.setFillColor(CGColor(gray: 1, alpha: 1))
        bitmap.fill(CGRect(x: 0, y: 0, width: width, height: height))
        bitmap.scaleBy(x: CGFloat(width) / media.width, y: CGFloat(height) / media.height)
        bitmap.translateBy(x: -media.minX, y: -media.minY)
        bitmap.drawPDFPage(page)
        guard let image = bitmap.makeImage() else {
            output.closePDF()
            return nil
        }

        let destination = CGRect(x: 0, y: 0, width: media.width, height: media.height)
        output.beginPDFPage([kCGPDFContextMediaBox as String: destination] as CFDictionary)
        output.draw(image, in: destination)
        output.endPDFPage()
        if CFDataGetLength(outputData) > maxOutputBytes {
            output.closePDF()
            return nil
        }
    }
    output.closePDF()
    let result = outputData as Data
    guard !result.isEmpty, result.count <= maxOutputBytes else { return nil }
    return result
}

// Only a successful complete conversion emits bytes. No user filenames,
// links, original annotations, or source metadata enter the generated PDF.
var input = Data()
while input.count <= maxInputBytes {
    let remaining = maxInputBytes + 1 - input.count
    let fragment = FileHandle.standardInput.readData(ofLength: min(65536, remaining))
    if fragment.isEmpty { break }
    input.append(fragment)
}
guard input.count <= maxInputBytes,
      let output = convert(input) else { exit(EXIT_FAILURE) }
FileHandle.standardOutput.write(output)
