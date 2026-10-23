import Foundation
import AVFoundation
import AudioToolbox
import CoreAudio
import Darwin

func event(_ name: String, _ fields: [String: Any] = [:]) {
    var row = fields; row["event"] = name
    if let data = try? JSONSerialization.data(withJSONObject: row) {
        FileHandle.standardError.write(data + Data([10]))
    }
}
func property(_ device: AudioObjectID, _ selector: AudioObjectPropertySelector, _ scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal) -> UInt32 {
    var address = AudioObjectPropertyAddress(mSelector: selector, mScope: scope, mElement: kAudioObjectPropertyElementMain)
    var value: UInt32 = 0; var size = UInt32(MemoryLayout<UInt32>.size)
    AudioObjectGetPropertyData(device, &address, 0, nil, &size, &value)
    return value
}
func devices() -> [[String: Any]] {
    var address = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyDevices, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
    var size: UInt32 = 0
    AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size)
    var ids = [AudioDeviceID](repeating: 0, count: Int(size) / MemoryLayout<AudioDeviceID>.size)
    AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &ids)
    return ids.map { id in
        var a = AudioObjectPropertyAddress(mSelector: kAudioObjectPropertyName, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
        var name: Unmanaged<CFString>?; var s = UInt32(MemoryLayout<CFString>.size)
        AudioObjectGetPropertyData(id, &a, 0, nil, &s, &name)
        func channels(_ scope: AudioObjectPropertyScope) -> Bool {
            var a = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyStreamConfiguration, mScope: scope, mElement: kAudioObjectPropertyElementMain)
            var bytes: UInt32 = 0
            guard AudioObjectGetPropertyDataSize(id, &a, 0, nil, &bytes) == noErr, bytes > 0 else { return false }
            let mem = UnsafeMutableRawPointer.allocate(byteCount: Int(bytes), alignment: MemoryLayout<AudioBufferList>.alignment)
            defer { mem.deallocate() }
            guard AudioObjectGetPropertyData(id, &a, 0, nil, &bytes, mem) == noErr else { return false }
            let list = UnsafeMutableAudioBufferListPointer(mem.assumingMemoryBound(to: AudioBufferList.self))
            return list.reduce(0) { $0 + Int($1.mNumberChannels) } > 0
        }
        return ["id": id, "name": name?.takeUnretainedValue() as String? ?? "unknown", "input": channels(kAudioDevicePropertyScopeInput), "output": channels(kAudioDevicePropertyScopeOutput)]
    }
}
func preferred(_ list: [[String: Any]], _ kind: String, _ selector: AudioObjectPropertySelector) -> AudioDeviceID {
    if let item = list.first(where: { ($0["name"] as? String ?? "").lowercased().contains("jabra") && $0[kind] as? Bool == true }) { return item["id"] as! AudioDeviceID }
    return property(AudioObjectID(kAudioObjectSystemObject), selector)
}
func assign(_ node: AVAudioIONode, _ device: AudioDeviceID) throws {
    guard let unit = node.audioUnit else { throw NSError(domain: "audio-unit", code: 1) }
    var value = device
    let status = AudioUnitSetProperty(unit, kAudioOutputUnitProperty_CurrentDevice, kAudioUnitScope_Global, 0, &value, UInt32(MemoryLayout<AudioDeviceID>.size))
    if status != noErr { throw NSError(domain: "device-route", code: Int(status)) }
}
let args = CommandLine.arguments
if args.contains("--devices") {
    let data = try JSONSerialization.data(withJSONObject: ["devices": devices(), "microphone_permission": AVCaptureDevice.authorizationStatus(for: .audio).rawValue])
    print(String(data: data, encoding: .utf8)!); exit(0)
}
if let index = args.firstIndex(of: "--supervise"), args.count > index + 2 {
    let child = Process(); child.executableURL = URL(fileURLWithPath: args[index+1]); child.arguments = Array(args[(index+2)...])
    try child.run()
    signal(SIGTERM, SIG_IGN); signal(SIGINT, SIG_IGN)
    let term = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .global())
    term.setEventHandler { child.terminate() }; term.resume()
    child.waitUntilExit(); exit(child.terminationStatus)
}
let engine = AVAudioEngine()
let player = AVAudioPlayerNode()
let list = devices()
let capture = !args.contains("--play") && !args.contains("--output-only")
if capture {
    let inputID = preferred(list, "input", kAudioHardwarePropertyDefaultInputDevice)
    guard inputID != 0 else { event("no_input"); exit(75) }
    let status = AVCaptureDevice.authorizationStatus(for: .audio)
    if status == .notDetermined {
        event("microphone_permission_required")
        AVCaptureDevice.requestAccess(for: .audio) { allowed in exit(allowed ? 75 : 77) }
        RunLoop.main.run()
        exit(77)
    }
    guard status == .authorized else { event("microphone_permission_required"); exit(77) }
    do {
        try assign(engine.inputNode, inputID)
        try engine.inputNode.setVoiceProcessingEnabled(true)
        try assign(engine.inputNode, inputID)
    } catch { event("input_setup_failed"); exit(75) }
}
let outputID = preferred(list, "output", kAudioHardwarePropertyDefaultOutputDevice)
do { try assign(engine.outputNode, outputID) } catch { event("output_setup_failed"); exit(75) }
engine.attach(player)
engine.connect(player, to: engine.mainMixerNode, format: nil)
let outputFormat = engine.outputNode.inputFormat(forBus: 0)
engine.connect(engine.mainMixerNode, to: engine.outputNode, format: outputFormat)
if capture {
    let node = engine.inputNode
    let source = node.outputFormat(forBus: 0)
    guard source.sampleRate > 0, source.channelCount > 0,
          let target = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16000, channels: 1, interleaved: true),
          let converter = AVAudioConverter(from: source, to: target) else { event("invalid_input_format"); exit(75) }
    node.installTap(onBus: 0, bufferSize: 2048, format: source) { buffer, _ in
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * 16000 / source.sampleRate + 16)
        guard let pcm = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: capacity) else { return }
        var provided = false; var error: NSError?
        converter.convert(to: pcm, error: &error) { _, status in
            if provided { status.pointee = .noDataNow; return nil }
            provided = true; status.pointee = .haveData; return buffer
        }
        if error == nil, let ptr = pcm.int16ChannelData?[0], pcm.frameLength > 0 {
            FileHandle.standardOutput.write(Data(bytes: ptr, count: Int(pcm.frameLength) * 2))
        }
    }
}
do { try engine.start() } catch { event("engine_start_failed"); exit(75) }
event("audio_ready", ["capture": capture, "echo_cancelled": capture && engine.inputNode.isVoiceProcessingEnabled, "output_id": outputID])
var playbackGeneration = 0
func play(_ path: String) {
    do {
        let file = try AVAudioFile(forReading: URL(fileURLWithPath: path))
        playbackGeneration += 1; let generation = playbackGeneration
        player.stop()
        engine.disconnectNodeOutput(player)
        engine.connect(player, to: engine.mainMixerNode, format: file.processingFormat)
        player.scheduleFile(file, at: nil, completionCallbackType: .dataPlayedBack) { _ in
            DispatchQueue.main.async { if generation == playbackGeneration { event("playback_done"); if args.contains("--play") { exit(0) } } }
        }
        player.play(); event("playback_started")
    } catch { event("playback_failed") }
}
if let i = args.firstIndex(of: "--play"), args.count > i+1 { play(args[i+1]) }
else {
    DispatchQueue.global().async {
        while let line = readLine() {
            guard let data = line.data(using: .utf8), let row = try? JSONSerialization.jsonObject(with: data) as? [String: String] else { continue }
            DispatchQueue.main.async {
                if row["op"] == "stop" { playbackGeneration += 1; player.stop(); event("playback_done") }
                if row["op"] == "play", let path = row["path"] { play(path) }
            }
        }
        exit(0)
    }
}
for selector in [kAudioHardwarePropertyDevices, kAudioHardwarePropertyDefaultInputDevice, kAudioHardwarePropertyDefaultOutputDevice] {
    var a = AudioObjectPropertyAddress(mSelector: selector, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
    AudioObjectAddPropertyListenerBlock(AudioObjectID(kAudioObjectSystemObject), &a, DispatchQueue.main) { _, _ in
        event("devices_changed"); exit(75)
    }
}
RunLoop.main.run()
