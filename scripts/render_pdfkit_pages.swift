import AppKit
import PDFKit

let arguments = CommandLine.arguments
guard arguments.count == 4,
      let dpi = Double(arguments[3]),
      let document = PDFDocument(url: URL(fileURLWithPath: arguments[1])) else {
    fatalError("usage: render_pdfkit_pages.swift input.pdf output-directory dpi")
}

let output = URL(fileURLWithPath: arguments[2], isDirectory: true)
let scale = CGFloat(dpi / 72)

for index in 0..<document.pageCount {
    guard let page = document.page(at: index) else { continue }
    let bounds = page.bounds(for: .mediaBox)
    let width = Int((bounds.width * scale).rounded())
    let height = Int((bounds.height * scale).rounded())
    guard let context = CGContext(
        data: nil,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: 0,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
    ) else { continue }

    context.setFillColor(NSColor.white.cgColor)
    context.fill(CGRect(x: 0, y: 0, width: width, height: height))
    context.scaleBy(x: scale, y: scale)
    page.draw(with: .mediaBox, to: context)

    guard let image = context.makeImage(),
          let data = NSBitmapImageRep(cgImage: image).representation(
              using: .png,
              properties: [:]
          ) else { continue }
    let filename = String(format: "page-%04d.png", index + 1)
    try data.write(to: output.appendingPathComponent(filename))
}
