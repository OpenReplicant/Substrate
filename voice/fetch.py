"""The voice head's model files (S-147), each checked against its SHA-256 as in the trial
(scripts/trials/voice-head/sha256.lock for the two kokoro-onnx files, which publish none). Fetched once into MODELS.

    python3 -I fetch.py MODELS
"""
import hashlib
import sys
import tarfile
import urllib.request
from pathlib import Path

GH = "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
KO = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FILES = [
    (GH + "asr-models/sherpa-onnx-nemo-parakeet_tdt_transducer_110m-en-36000-int8.tar.bz2", "parakeet-110m.tar.bz2",
     "f628312e9fdf8686374cb01a69425c41732529d540860311f16f37cbc32cfe9b"),
    (GH + "asr-models/silero_vad.onnx", "silero_vad.onnx", "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6"),
    (KO + "kokoro-v1.0.int8.onnx", "kokoro-v1.0.int8.onnx", "6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb"),
    (KO + "voices-v1.0.bin", "voices-v1.0.bin", "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"),
]


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    root = Path(sys.argv[1])
    root.mkdir(parents=True, exist_ok=True)
    for url, rel, want in FILES:
        dest = root / rel
        if not dest.exists():
            print(f"voice: fetching {rel}", flush=True)
            tmp = dest.with_suffix(dest.suffix + ".part")
            urllib.request.urlretrieve(url, tmp)
            if sha(tmp) != want:
                tmp.unlink()
                sys.exit(f"voice: {rel} does not match its SHA-256 {want}; removed")
            tmp.rename(dest)
        if rel.endswith(".tar.bz2") and not (root / "parakeet-110m").exists():
            with tarfile.open(dest) as t:
                t.extractall(root / "parakeet-110m.tmp", filter="data")
            (root / "parakeet-110m.tmp").rename(root / "parakeet-110m")
    print("voice: models ready", flush=True)


if __name__ == "__main__":
    main()
