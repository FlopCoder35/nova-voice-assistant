class PCMProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        // 16kHz audio. Buffer of 2048 frames is ~128ms. 
        // This is within the 80ms to 200ms range required by the prompt.
        this.bufferSize = 2048; 
        this.buffer = new Float32Array(this.bufferSize);
        this.bufferIndex = 0;
    }

    process(inputs, outputs, parameters) {
        const input = inputs[0];
        if (input && input.length > 0) {
            const channelData = input[0];
            
            let sumSquares = 0;
            for (let i = 0; i < channelData.length; i++) {
                sumSquares += channelData[i] * channelData[i];
                this.buffer[this.bufferIndex++] = channelData[i];
                
                // When buffer is full, convert to 16-bit PCM and send to main thread
                if (this.bufferIndex >= this.bufferSize) {
                    const pcm16 = new Int16Array(this.bufferSize);
                    for (let j = 0; j < this.bufferSize; j++) {
                        let s = Math.max(-1, Math.min(1, this.buffer[j]));
                        // Convert Float32 [-1.0, 1.0] to Int16 [-32768, 32767]
                        pcm16[j] = s < 0 ? s * 0x8000 : s * 0x7FFF;
                    }
                    // Send to main thread
                    this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
                    this.bufferIndex = 0;
                }
            }
            
            // Native RMS metering to instantly detect user interruption
            const rms = Math.sqrt(sumSquares / channelData.length);
            if (rms > 0.05) {
                this.port.postMessage('user_speaking');
            }
        }
        return true;
    }
}

registerProcessor('pcm-processor', PCMProcessor);
