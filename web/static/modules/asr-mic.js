// Legacy stub — ASR mic not yet ported to TS.
// The TS prototype (chat_ts.html) includes the mic button in the template
// but doesn't wire it. Future work: port to TS under web/src_ts/asr/.

const C = { IDLE: 'asr-mic-idle', RECORDING: 'asr-mic-recording', TRANSCRIBING: 'asr-mic-transcribing' };

export function initAsrMic(deps) {}
export function startRecording() {}
export function stopRecording() {}
export function destroy() {}
