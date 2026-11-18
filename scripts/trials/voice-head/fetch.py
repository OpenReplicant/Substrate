"""The voice head trial's model files, each checked against its SHA-256: the one its publisher lists (GitHub's
release digest, Hugging Face's LFS hash), or, where none is published, the one recorded in sha256.lock on the
first fetch (trust on first use, then checked every time). Into .state/trials/voice-head/models.

    python3 -I fetch.py MODELS_DIR
"""
import hashlib
import sys
import tarfile
import urllib.request
from pathlib import Path

HF = "https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/8f23f0c03c8761650bdb5b40aaf3e40d2c15f1ce/"
GH = "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
KO = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FILES = [
    # onnx-asr's Parakeet TDT 0.6B v3, int8 (CC-BY-4.0)
    (HF + "encoder-model.int8.onnx", "onnx-asr-parakeet-v3/encoder-model.int8.onnx", "6139d2fa7e1b086097b277c7149725edbab89cc7c7ae64b23c741be4055aff09"),
    (HF + "decoder_joint-model.int8.onnx", "onnx-asr-parakeet-v3/decoder_joint-model.int8.onnx", "eea7483ee3d1a30375daedc8ed83e3960c91b098812127a0d99d1c8977667a70"),
    (HF + "nemo128.onnx", "onnx-asr-parakeet-v3/nemo128.onnx", "a9fde1486ebfcc08f328d75ad4610c67835fea58c73ba57e3209a6f6cf019e9f"),
    (HF + "config.json", "onnx-asr-parakeet-v3/config.json", None),
    (HF + "vocab.txt", "onnx-asr-parakeet-v3/vocab.txt", None),
    # sherpa-onnx's Parakeet TDT 0.6B v3 and 110M, int8; Silero VAD; Kokoro v1.0 int8
    (GH + "asr-models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2", "sherpa-parakeet-v3.tar.bz2", "1495e91b59d7fc53ddca91f3431758ec99f8fa253fdb0e1e851be0f72b14b0f9"),
    (GH + "asr-models/sherpa-onnx-nemo-parakeet_tdt_transducer_110m-en-36000-int8.tar.bz2", "sherpa-parakeet-110m.tar.bz2", "f628312e9fdf8686374cb01a69425c41732529d540860311f16f37cbc32cfe9b"),
    (GH + "asr-models/silero_vad.onnx", "silero_vad.onnx", "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6"),
    (GH + "asr-models/test_silero_vad.wav", "test_silero_vad.wav", "89f17d9c94c4b31eb320f424628bcbc920abaddbee6e2760fd868bfb1d9a2e47"),
    (GH + "tts-models/kokoro-int8-multi-lang-v1_0.tar.bz2", "sherpa-kokoro.tar.bz2", "72c347230107ef8a31098ec4d468a605244beef5f1ed00db97efa13518800653"),
    # real speech with transcripts: 73 LibriSpeech validation-clean utterances (CC-BY-4.0), Hugging Face's sample
    ("https://huggingface.co/datasets/hf-internal-testing/librispeech_asr_dummy/resolve/5be91486e11a2d616f4ec5db8d3fd248585ac07a/clean/validation-00000-of-00001.parquet",
     "librispeech-dummy.parquet", "4e69a06fa5edc90921e5e7e39a7084881f8b3ed9c805c574f4f39c6fde27c603"),
    # kokoro-onnx's Kokoro v1.0 int8 and voices (Apache-2.0)
    (KO + "kokoro-v1.0.int8.onnx", "kokoro-onnx/kokoro-v1.0.int8.onnx", None),
    (KO + "voices-v1.0.bin", "kokoro-onnx/voices-v1.0.bin", None),
]
LOCK = Path(__file__).with_name("sha256.lock")


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    root = Path(sys.argv[1])
    lock = dict(l.split("  ", 1)[::-1] for l in LOCK.read_text().splitlines() if l.strip()) if LOCK.exists() else {}
    for url, rel, want in FILES:
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            print(f"fetch {rel}", flush=True)
            tmp = dest.with_suffix(dest.suffix + ".part")
            urllib.request.urlretrieve(url, tmp)
            tmp.rename(dest)
        got = sha(dest)
        want = want or lock.get(rel)
        if want and got != want:
            dest.unlink()
            sys.exit(f"{rel}: SHA-256 {got}, expected {want}; removed")
        if not want:
            lock[rel] = got
            print(f"  {rel}: no published checksum; recorded {got[:16]}... in sha256.lock")
        if rel.endswith(".tar.bz2") and not (root / (rel[:-8] + ".d")).exists():
            with tarfile.open(dest) as t:
                t.extractall(root / (rel[:-8] + ".d"), filter="data")
    LOCK.write_text("".join(f"{v}  {k}\n" for k, v in sorted(lock.items())))
    print("models ready")


if __name__ == "__main__":
    main()
