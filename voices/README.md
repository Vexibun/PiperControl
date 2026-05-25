# Piper Voices

This directory contains the voice models used by Piper TTS.

## Getting Voices

Piper supports a variety of voices in multiple languages. Download voices from:

**Official Piper Repository:**
- https://github.com/rhasspy/piper/releases/
- Look for files named like: `en_US-amy-medium.onnx` and `en_US-amy-medium.onnx.json`

**Alternative Voice Sources:**
- HuggingFace: https://huggingface.co/rhasspy/piper-voices/tree/main
- Piper Voices Database: https://piper.rhasspy.org/

## Installation

1. Download voice files from one of the sources above
2. Each voice requires **two files**:
   - `{voice-name}.onnx` - The neural network model
   - `{voice-name}.onnx.json` - The voice configuration metadata

3. Place both files in this `voices/` directory
4. The application will automatically detect and list them in the Voice dropdown

## Example

To add the "Amy" voice in English (US):

```
voices/
├── en_US-amy-medium.onnx
└── en_US-amy-medium.onnx.json
```

## Available Voice Models

Piper includes voices for multiple languages and speakers:

- **English (US):** amy, arctic, hfc_female, trump
- **English (GB):** alan, cori
- **Portuguese (BR):** cadu
- **Portuguese (PT):** dii
- **Spanish (MX):** claude
- **Special Voices:** glados, alexa, cortana, google_assistant, kronk, biofects_prime

## File Structure

Each voice model consists of:

- **`.onnx` file** - The actual neural network model (quantized for efficiency)
  - Size: typically 100-300 MB
  - Required: Yes

- **`.onnx.json` file** - Configuration including:
  - Phoneme configuration
  - Sample rate
  - Number of speakers (if multi-speaker)
  - Model metadata
  - Required: Yes

## Notes

- Voice files are NOT tracked in git (they're large and user-specific)
- You need to download and place them manually
- The application will work with any valid Piper voice model
- Having more voices takes up more disk space but doesn't affect performance

## Troubleshooting

If a voice doesn't appear in the dropdown:
- Verify both `.onnx` and `.onnx.json` files are present
- Check the file names match exactly (case-sensitive on Linux/Mac)
- Restart the application after adding new voices
