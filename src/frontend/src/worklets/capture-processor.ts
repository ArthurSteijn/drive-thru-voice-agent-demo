// AudioWorklet global types
declare class AudioWorkletProcessor {
  readonly port: MessagePort;
  process(inputs: Float32Array[][], outputs: Float32Array[][], parameters: Record<string, Float32Array>): boolean;
}
declare function registerProcessor(name: string, ctor: new () => AudioWorkletProcessor): void;

/**
 * AudioWorklet processor that captures PCM16 mono audio at the
 * worklet's sample rate and posts Float32 chunks to the main thread.
 *
 * The main thread is responsible for resampling to 24 kHz and
 * converting to Int16 before sending over the WebSocket.
 */
class CaptureProcessor extends AudioWorkletProcessor {
  process(inputs: Float32Array[][]) {
    const input = inputs[0];
    if (input && input[0] && input[0].length > 0) {
      this.port.postMessage(new Float32Array(input[0]));
    }
    return true;
  }
}

registerProcessor("capture-processor", CaptureProcessor);
