# NAM Reamp Asset

Place `T3K-sweep-v3.wav` in this directory during image build. The engine will
automatically pick it up.

## Obtaining the file

Download the standardized reamp signal from the Neural Amp Modeler trainer:

1. Go to <https://tone3000.com/capture> (or the NAM Colab notebook).
2. Click **"Download input file"** — this gives you `T3K-sweep-v3.wav`.
3. Verify: 24-bit PCM, 48 000 Hz, mono, ~3 minutes long.
4. Copy it here as `setup/nam/T3K-sweep-v3.wav`.

The file is not committed to this repository to keep the repo lightweight.

## Format

| Property    | Value       |
|-------------|-------------|
| Sample rate | 48 000 Hz   |
| Bit depth   | 24-bit PCM  |
| Channels    | Mono (1)    |
| Container   | WAV         |
