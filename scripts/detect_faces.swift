// Face rectangles + landmarks for a folder of frames, via macOS Vision (no extra installs).
// Used by face_beauty.py to build a skin-only mask that protects eyes, brows, glasses and lips.
//
// Build:  swiftc -O detect_faces.swift -o detect_faces
//         If the compiler complains the SDK is newer than the compiler, pick an older SDK, e.g.
//         swiftc -O -sdk /Library/Developer/CommandLineTools/SDKs/MacOSX15.sdk detect_faces.swift -o detect_faces
// Usage:  detect_faces <frames_dir> <out.json>
// Output: { "frame.jpg": [ {"box":[x,y,w,h], "regions":{name:[[x,y],...]}} ] }
// All coordinates normalised to the image, origin top-left.
import AppKit
import Foundation
import Vision

guard CommandLine.arguments.count == 3 else {
    fputs("usage: detect_faces <frames_dir> <out.json>\n", stderr); exit(2)
}
let dir = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let files = try FileManager.default.contentsOfDirectory(atPath: dir.path)
    .filter { $0.lowercased().hasSuffix(".jpg") || $0.lowercased().hasSuffix(".png") }.sorted()
var result: [String: Any] = [:]

for name in files {
    let url = dir.appendingPathComponent(name)
    guard let src = CGImageSourceCreateWithURL(url as CFURL, nil),
          let img = CGImageSourceCreateImageAtIndex(src, 0, nil) else { continue }
    let req = VNDetectFaceLandmarksRequest()
    try? VNImageRequestHandler(cgImage: img, options: [:]).perform([req])
    var faces: [[String: Any]] = []
    for f in req.results ?? [] {
        let b = f.boundingBox  // normalised, origin bottom-left
        var regions: [String: [[Double]]] = [:]
        if let lm = f.landmarks {
            let named: [(String, VNFaceLandmarkRegion2D?)] = [
                ("faceContour", lm.faceContour), ("leftEye", lm.leftEye), ("rightEye", lm.rightEye),
                ("leftEyebrow", lm.leftEyebrow), ("rightEyebrow", lm.rightEyebrow),
                ("outerLips", lm.outerLips), ("nose", lm.nose)]
            for (key, region) in named {
                guard let r = region else { continue }
                regions[key] = r.normalizedPoints.map { p in
                    let x = Double(b.origin.x + CGFloat(p.x) * b.width)
                    let y = Double(b.origin.y + CGFloat(p.y) * b.height)
                    return [x, 1 - y]
                }
            }
        }
        faces.append(["box": [Double(b.origin.x), Double(1 - b.origin.y - b.height), Double(b.width), Double(b.height)],
                      "confidence": Double(f.confidence), "regions": regions])
    }
    result[name] = faces
}
let data = try JSONSerialization.data(withJSONObject: result, options: [])
try data.write(to: URL(fileURLWithPath: CommandLine.arguments[2]))
print("frames \(files.count), with faces \(result.values.filter { ($0 as! [Any]).count > 0 }.count)")
