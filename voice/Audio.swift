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
func selectDefault(_ selector: AudioObjectPropertySelector, _ device: AudioDeviceID) throws {
    let system = AudioObjectID(kAudioObjectSystemObject)
    if device == 0 || property(system, selector) == device { return }
    var address = AudioObjectPropertyAddress(mSelector: selector, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
    var value = device
    let status = AudioObjectSetPropertyData(system, &address, 0, nil, UInt32(MemoryLayout<AudioDeviceID>.size), &value)
    if status != noErr { throw NSError(domain: "default-device-route", code: Int(status)) }
}
func currentDevice(_ node: AVAudioIONode) -> UInt32 {
    guard let unit = node.audioUnit else { return 0 }
    var device: UInt32 = 0; var size = UInt32(MemoryLayout<UInt32>.size)
    AudioUnitGetProperty(unit, kAudioOutputUnitProperty_CurrentDevice, kAudioUnitScope_Global, 0, &device, &size)
    return device
}
func formatFields(_ format: AVAudioFormat) -> [String: Any] {
    return ["sample_rate": format.sampleRate, "channels": format.channelCount,
            "common_format": format.commonFormat.rawValue, "interleaved": format.isInterleaved]
}
func routeFields(_ engine: AVAudioEngine, _ inputID: AudioDeviceID, _ outputID: AudioDeviceID, _ capture: Bool) -> [String: Any] {
    var fields: [String: Any] = ["input_id": inputID, "output_id": outputID,
        "input_name": devices().first(where: { $0["id"] as? UInt32 == inputID })?["name"] ?? "none",
        "output_name": devices().first(where: { $0["id"] as? UInt32 == outputID })?["name"] ?? "none",
        "default_input_id": property(AudioObjectID(kAudioObjectSystemObject), kAudioHardwarePropertyDefaultInputDevice),
        "default_output_id": property(AudioObjectID(kAudioObjectSystemObject), kAudioHardwarePropertyDefaultOutputDevice),
        "output_au_device": currentDevice(engine.outputNode),
        "output_input_format": formatFields(engine.outputNode.inputFormat(forBus: 0)),
        "output_hardware_format": formatFields(engine.outputNode.outputFormat(forBus: 0))]
    if capture {
        fields["input_au_device"] = currentDevice(engine.inputNode)
        fields["input_hardware_format"] = formatFields(engine.inputNode.inputFormat(forBus: 0))
        fields["input_output_format"] = formatFields(engine.inputNode.outputFormat(forBus: 0))
        fields["shared_io_unit"] = engine.inputNode.audioUnit == engine.outputNode.audioUnit
    }
    return fields
}
func eventError(_ name: String, _ error: Error, _ fields: [String: Any] = [:]) {
    let error = error as NSError
    var row = fields
    row["error_domain"] = error.domain; row["error_code"] = error.code
    row["error_description"] = error.localizedDescription
    row["error_debug_description"] = error.userInfo[NSDebugDescriptionErrorKey] as? String ?? ""
    if let underlying = error.userInfo[NSUnderlyingErrorKey] as? NSError {
        row["underlying_error_domain"] = underlying.domain; row["underlying_error_code"] = underlying.code
    }
    event(name, row)
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
let list = devices()
let capture = !args.contains("--play") && !args.contains("--output-only")
let inputID = capture ? preferred(list, "input", kAudioHardwarePropertyDefaultInputDevice) : 0
let outputID = preferred(list, "output", kAudioHardwarePropertyDefaultOutputDevice)
// VoiceProcessingIO shares one AudioUnit between both nodes. Let CoreAudio build
// its duplex device from the default pair; assigning each node overwrites the
// same CurrentDevice property and disconnects one side of a split USB device.
do {
    if capture { try selectDefault(kAudioHardwarePropertyDefaultInputDevice, inputID) }
    try selectDefault(kAudioHardwarePropertyDefaultOutputDevice, outputID)
} catch { eventError("device_selection_failed", error); exit(75) }
let engine = AVAudioEngine()
let player = AVAudioPlayerNode()
if capture {
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
        try engine.inputNode.setVoiceProcessingEnabled(true)
    } catch { eventError("input_setup_failed", error); exit(75) }
}
engine.attach(player)
engine.connect(player, to: engine.mainMixerNode, format: nil)
// Voice processing requires identical formats on the input and output sides.
let outputFormat = capture ? engine.inputNode.outputFormat(forBus: 0) : engine.outputNode.inputFormat(forBus: 0)
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
event("engine_configured", routeFields(engine, inputID, outputID, capture))
do { try engine.start() } catch { eventError("engine_start_failed", error, routeFields(engine, inputID, outputID, capture)); exit(75) }
var readyFields = routeFields(engine, inputID, outputID, capture)
readyFields["capture"] = capture
readyFields["echo_cancelled"] = capture && engine.inputNode.isVoiceProcessingEnabled
event("audio_ready", readyFields)
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
