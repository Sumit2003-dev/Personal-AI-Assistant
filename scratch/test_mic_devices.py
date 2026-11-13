import sounddevice as sd
import numpy as np

print("Default Input Device:", sd.default.device[0])
devices = sd.query_devices()
for idx, d in enumerate(devices):
    if d['max_input_channels'] > 0:
        print(f"Input Device {idx}: {d['name']} (channels: {d['max_input_channels']})")

rec = sd.rec(16000, samplerate=16000, channels=1, dtype='float32')
sd.wait()
audio = rec.flatten()
peak = float(np.max(np.abs(audio)))
rms = float(np.sqrt(np.mean(audio**2)))
print(f"Test 1s Capture: Peak Amplitude={peak:.6f}, RMS Volume={rms:.6f}")

