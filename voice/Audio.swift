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
func deviceUID(_ device: AudioDeviceID) throws -> CFString {
    var address = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyDeviceUID, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
    var uid: Unmanaged<CFString>?
    var size = UInt32(MemoryLayout<CFString>.size)
    let status = AudioObjectGetPropertyData(device, &address, 0, nil, &size, &uid)
    if status != noErr { throw NSError(domain: "device-uid", code: Int(status)) }
    guard let uid = uid else { throw NSError(domain: "device-uid", code: 75) }
    return uid.takeUnretainedValue()
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
func streamFields(_ format: AudioStreamBasicDescription) -> [String: Any] {
    return ["sample_rate": format.mSampleRate, "channels": format.mChannelsPerFrame,
            "format_id": format.mFormatID, "format_flags": format.mFormatFlags,
            "bits_per_channel": format.mBitsPerChannel, "bytes_per_frame": format.mBytesPerFrame]
}
func routeFields(_ engine: AVAudioEngine, _ inputID: AudioDeviceID, _ outputID: AudioDeviceID, _ capture: Bool) -> [String: Any] {
    let selected = devices()
    let inputName = selected.first(where: { $0["id"] as? UInt32 == inputID })?["name"] as? String ?? "none"
    let outputName = selected.first(where: { $0["id"] as? UInt32 == outputID })?["name"] as? String ?? "none"
    let hardwareAEC = capture && inputName.lowercased().contains("jabra") && inputName == outputName
        && property(inputID, kAudioDevicePropertyTransportType) == kAudioDeviceTransportTypeUSB
        && property(outputID, kAudioDevicePropertyTransportType) == kAudioDeviceTransportTypeUSB
    return ["input_id": inputID, "output_id": outputID,
        "input_name": inputName, "output_name": outputName,
        "default_input_id": property(AudioObjectID(kAudioObjectSystemObject), kAudioHardwarePropertyDefaultInputDevice),
        "default_output_id": property(AudioObjectID(kAudioObjectSystemObject), kAudioHardwarePropertyDefaultOutputDevice),
        "output_au_device": currentDevice(engine.outputNode),
        "output_input_format": formatFields(engine.outputNode.inputFormat(forBus: 0)),
        "output_hardware_format": formatFields(engine.outputNode.outputFormat(forBus: 0)),
        "capture": capture, "echo_cancelled": hardwareAEC,
        "echo_cancellation": hardwareAEC ? "jabra_usb_hardware" : "unavailable",
        "capture_method": capture ? "audio_queue" : "none",
        "microphone_permission": AVCaptureDevice.authorizationStatus(for: .audio).rawValue]
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
let debugAudio = args.contains("--debug-audio")
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
}
// A direct input queue avoids the unintelligible VoiceProcessingIO duplex
// route on this split USB device. The duplex USB Jabra route uses the
// speakerphone's hardware AEC. Other routes keep playback wake detection gated.
// Playback uses a separate, explicitly selected output unit. Neither side
// changes the system defaults or follows an AirPods default-device switch.
let engine = AVAudioEngine()
let player = AVAudioPlayerNode()
do {
    guard outputID != 0, let unit = engine.outputNode.audioUnit else { throw NSError(domain: "no-output", code: 75) }
    var selectedOutput = outputID
    let status = AudioUnitSetProperty(unit, kAudioOutputUnitProperty_CurrentDevice, kAudioUnitScope_Global, 0, &selectedOutput, UInt32(MemoryLayout<AudioDeviceID>.size))
    if status != noErr { throw NSError(domain: "output-device-route", code: Int(status)) }
    guard currentDevice(engine.outputNode) == outputID else { throw NSError(domain: "output-device-mismatch", code: 75) }
} catch { eventError("device_selection_failed", error); exit(75) }
engine.attach(player)
engine.connect(player, to: engine.mainMixerNode, format: nil)
let outputFormat = engine.outputNode.inputFormat(forBus: 0)
engine.connect(engine.mainMixerNode, to: engine.outputNode, format: outputFormat)
var inputQueue: AudioQueueRef?
var inputUID: CFString = "" as CFString
var captureFormat = AudioStreamBasicDescription(mSampleRate: 16000, mFormatID: kAudioFormatLinearPCM,
    mFormatFlags: kLinearPCMFormatFlagIsSignedInteger | kLinearPCMFormatFlagIsPacked,
    mBytesPerPacket: 2, mFramesPerPacket: 1, mBytesPerFrame: 2, mChannelsPerFrame: 1,
    mBitsPerChannel: 16, mReserved: 0)
var debugStarted = ProcessInfo.processInfo.systemUptime
var debugBuffers = 0, debugFrames = 0
var debugPower = 0.0
func checkQueue(_ status: OSStatus, _ operation: String) throws {
    if status != noErr { throw NSError(domain: operation, code: Int(status)) }
}
if capture {
    do {
        inputUID = try deviceUID(inputID)
        try checkQueue(AudioQueueNewInput(&captureFormat, { _, queue, buffer, _, _, _ in
            let byteCount = Int(buffer.pointee.mAudioDataByteSize)
            FileHandle.standardOutput.write(Data(bytes: buffer.pointee.mAudioData, count: byteCount))
            if debugAudio {
                let samples = buffer.pointee.mAudioData.assumingMemoryBound(to: Int16.self)
                let frames = byteCount / 2
                debugBuffers += 1; debugFrames += frames
                for frame in 0..<frames {
                    let value = Double(samples[frame]) / 32768
                    debugPower += value * value
                }
                let now = ProcessInfo.processInfo.systemUptime
                if now - debugStarted >= 5 {
                    event("native_audio_debug", ["capture_method": "audio_queue", "input_frames": debugFrames,
                        "converted_frames": debugFrames, "tap_buffers": debugBuffers,
                        "source_channel_rms": [sqrt(debugPower / Double(max(debugFrames, 1)))]])
                    debugStarted = now; debugBuffers = 0; debugFrames = 0; debugPower = 0
                }
            }
            let status = AudioQueueEnqueueBuffer(queue, buffer, 0, nil)
            if status != noErr { event("capture_enqueue_failed", ["error_code": status]); exit(75) }
        }, nil, CFRunLoopGetMain(), CFRunLoopMode.commonModes.rawValue, 0, &inputQueue), "capture-create")
        guard let queue = inputQueue else { throw NSError(domain: "capture-create", code: 75) }
        var uidReference = Unmanaged.passUnretained(inputUID)
        try checkQueue(AudioQueueSetProperty(queue, kAudioQueueProperty_CurrentDevice, &uidReference, UInt32(MemoryLayout<CFString>.size)), "capture-device-route")
        for _ in 0..<3 {
            var buffer: AudioQueueBufferRef?
            // Forty milliseconds bounds native capture delivery for interruption.
            try checkQueue(AudioQueueAllocateBuffer(queue, 1280, &buffer), "capture-allocate")
            guard let buffer = buffer else { throw NSError(domain: "capture-allocate", code: 75) }
            try checkQueue(AudioQueueEnqueueBuffer(queue, buffer, 0, nil), "capture-enqueue")
        }
    } catch { eventError("input_setup_failed", error); exit(75) }
}
event("engine_configured", routeFields(engine, inputID, outputID, capture))
do { try engine.start() } catch { eventError("engine_start_failed", error, routeFields(engine, inputID, outputID, capture)); exit(75) }
if let queue = inputQueue {
    do {
        try checkQueue(AudioQueueStart(queue, nil), "capture-start")
        var actualUIDReference: Unmanaged<CFString>?
        var size = UInt32(MemoryLayout<CFString>.size)
        try checkQueue(AudioQueueGetProperty(queue, kAudioQueueProperty_CurrentDevice, &actualUIDReference, &size), "capture-read-route")
        guard let actualUID = actualUIDReference?.takeUnretainedValue() else { throw NSError(domain: "capture-read-route", code: 75) }
        guard actualUID as String == inputUID as String else { throw NSError(domain: "capture-device-mismatch", code: 75) }
        size = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
        try checkQueue(AudioQueueGetProperty(queue, kAudioQueueProperty_StreamDescription, &captureFormat, &size), "capture-read-format")
        event("capture_audio_ready", ["input_id": inputID, "input_device_uid": actualUID as String,
            "input_name": list.first(where: { $0["id"] as? UInt32 == inputID })?["name"] ?? "none",
            "microphone_permission": AVCaptureDevice.authorizationStatus(for: .audio).rawValue,
            "capture_method": "audio_queue", "capture_format": streamFields(captureFormat)])
    } catch { eventError("capture_start_failed", error); exit(75) }
}
event("audio_ready", routeFields(engine, inputID, outputID, capture))
var playbackGeneration = 0
var playbackID = ""
var playbackDuration = 0.0
func playbackPosition() -> Double {
    guard let rendered = player.lastRenderTime,
          let position = player.playerTime(forNodeTime: rendered), position.sampleRate > 0 else { return 0 }
    return min(playbackDuration, max(0, Double(position.sampleTime) / position.sampleRate))
}
func playbackFields() -> [String: Any] {
    return ["play_id": playbackID, "native_at": Date().timeIntervalSince1970,
            "native_monotonic": ProcessInfo.processInfo.systemUptime,
            "position_seconds": playbackPosition(), "duration_seconds": playbackDuration]
}
func play(_ path: String, _ playID: String = UUID().uuidString) {
    do {
        let file = try AVAudioFile(forReading: URL(fileURLWithPath: path))
        playbackGeneration += 1; let generation = playbackGeneration
        playbackID = playID
        playbackDuration = Double(file.length) / file.processingFormat.sampleRate
        player.stop()
        engine.disconnectNodeOutput(player)
        engine.connect(player, to: engine.mainMixerNode, format: file.processingFormat)
        player.scheduleFile(file, at: nil, completionCallbackType: .dataPlayedBack) { _ in
            DispatchQueue.main.async { if generation == playbackGeneration { event("playback_done", playbackFields()); if args.contains("--play") { exit(0) } } }
        }
        player.play(); event("playback_started", playbackFields())
    } catch { event("playback_failed", ["play_id": playID]) }
}
if let i = args.firstIndex(of: "--play"), args.count > i+1 { play(args[i+1]) }
else {
    DispatchQueue.global().async {
        while let line = readLine() {
            guard let data = line.data(using: .utf8), let row = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { continue }
            DispatchQueue.main.async {
                let op = row["op"] as? String
                if op == "pause" || op == "stop" {
                    // stop() resets the sample timeline, so capture it first.
                    let position = playbackPosition()
                    if op == "pause" { player.pause() }
                    else { playbackGeneration += 1; player.stop() }
                    var fields = row
                    fields.removeValue(forKey: "op")
                    fields["stopped_at"] = Date().timeIntervalSince1970
                    fields["stopped_monotonic"] = ProcessInfo.processInfo.systemUptime
                    fields["stop_method"] = op == "pause" ? "player_pause" : "player_stop"
                    fields["position_seconds"] = position
                    fields["duration_seconds"] = playbackDuration
                    event("playback_stopped", fields)
                }
                if op == "resume", row["play_id"] as? String == playbackID {
                    player.play()
                    var fields = playbackFields(); fields["stop_id"] = row["stop_id"]
                    event("playback_resumed", fields)
                }
                if op == "play", let path = row["path"] as? String { play(path, row["play_id"] as? String ?? UUID().uuidString) }
            }
        }
        exit(0)
    }
}
let playbackProgress = DispatchSource.makeTimerSource(queue: .main)
playbackProgress.schedule(deadline: .now() + .milliseconds(200), repeating: .milliseconds(200))
playbackProgress.setEventHandler {
    if player.isPlaying { event("playback_progress", playbackFields()) }
}
playbackProgress.resume()
var deviceListAddress = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyDevices, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
AudioObjectAddPropertyListenerBlock(AudioObjectID(kAudioObjectSystemObject), &deviceListAddress, DispatchQueue.main) { _, _ in
    let available = devices()
    let inputPresent = !capture || available.contains(where: { $0["id"] as? UInt32 == inputID && $0["input"] as? Bool == true })
    let outputPresent = available.contains(where: { $0["id"] as? UInt32 == outputID && $0["output"] as? Bool == true })
    if !inputPresent || !outputPresent {
        event("selected_device_removed", ["input_id": inputID, "output_id": outputID,
            "input_present": inputPresent, "output_present": outputPresent]); exit(75)
    }
}
RunLoop.main.run()
