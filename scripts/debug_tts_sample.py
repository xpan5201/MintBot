"""Debug script: check end-to-end GPT-SoVITS TTS behavior for a complex sentence.

This script uses MintChat's TTSManager configuration to call GPT-SoVITS,
then prints basic statistics about the synthesized audio and saves it
as data/debug_tts_sample.wav for manual listening.
"""

import asyncio
import io
from pathlib import Path

import soundfile as sf

from src.config.settings import get_settings
from src.multimodal.tts_manager import TTSConfig, TTSManager


SAMPLE_TEXT = (
    "（（立刻扑进主人怀里，幸福地蹭蹭）喵~最喜欢和主人贴贴了！"
    "（用毛茸茸的脑袋轻蹭主人的脸颊）主人的怀抱最温暖了喵~）"
)


async def main() -> None:
    settings = get_settings()

    tts_settings = settings.tts

    config = TTSConfig(
        api_url=tts_settings.api_url,
        ref_audio_path=tts_settings.ref_audio_path,
        ref_audio_text=tts_settings.ref_audio_text,
        text_lang=tts_settings.text_lang,
        prompt_lang=tts_settings.prompt_lang,
        top_k=tts_settings.top_k,
        top_p=tts_settings.top_p,
        temperature=tts_settings.temperature,
        speed_factor=tts_settings.speed_factor,
        text_split_method=tts_settings.text_split_method,
        batch_size=getattr(tts_settings, "batch_size", 1),
        seed=getattr(tts_settings, "seed", -1),
    )

    manager = TTSManager(config)

    print("=== TTS DEBUG: INPUT TEXT ===")
    print(SAMPLE_TEXT)
    print("Length (chars):", len(SAMPLE_TEXT))

    audio = await manager.synthesize_text(SAMPLE_TEXT)

    if not audio:
        print("[ERROR] TTS returned no audio data.")
        return

    print("Raw audio bytes:", len(audio))

    # Decode with soundfile to inspect frames and duration
    data, samplerate = sf.read(io.BytesIO(audio), dtype="float32")
    if getattr(data, "ndim", 1) > 1:
        num_frames = data.shape[0]
    else:
        num_frames = len(data)

    duration = num_frames / float(samplerate)
    print("Samplerate:", samplerate)
    print("Frames:", num_frames)
    print("Duration (seconds):", duration)

    # Save to file for manual listening
    out_path = Path("data/audio/debug_tts_sample.wav")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), data, samplerate)
    print("Saved debug audio to:", out_path)


if __name__ == "__main__":
    asyncio.run(main())
