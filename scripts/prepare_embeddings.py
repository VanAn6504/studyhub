"""Download a frozen public pretrained ONNX checkpoint. No private content upload."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.local_embeddings import DIMENSION, MODEL_FILE, REPO, REVISION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.local' / 'embedding')
    directory = parser.parse_args().output.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=45, follow_redirects=True, trust_env=False) as client:
        metadata = client.get(f'https://huggingface.co/api/models/{REPO}/revision/{REVISION}?blobs=true')
        metadata.raise_for_status()
        info = {f['rfilename']: f for f in metadata.json()['siblings']}
        hashes = {}
        for remote, local in [(MODEL_FILE, 'model.onnx'), ('onnx/tokenizer.json', 'tokenizer.json')]:
            path = directory / local
            expected = info[remote].get('lfs', {}).get('sha256')
            if expected and path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
                print(f'{local}: verified existing artifact', flush=True)
            else:
                temporary = directory / (local + '.partial')
                print(f'Downloading {local} from frozen revision {REVISION[:12]}...', flush=True)
                try:
                    with client.stream('GET', f'https://huggingface.co/{REPO}/resolve/{REVISION}/{remote}') as response:
                        response.raise_for_status()
                        size = 0
                        with temporary.open('wb') as handle:
                            for block in response.iter_bytes():
                                size += len(block)
                                if size > 200_000_000:
                                    raise ValueError('Model exceeds size limit')
                                handle.write(block)
                    data = temporary.read_bytes()
                    if expected:
                        assert hashlib.sha256(data).hexdigest() == expected, 'Checkpoint digest mismatch'
                    else:
                        assert hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest() == info[remote]['blobId'], 'Tokenizer digest mismatch'
                    temporary.replace(path)
                finally:
                    temporary.unlink(missing_ok=True)
            hashes[local] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest = {'repo': REPO, 'revision': REVISION, 'model_file': MODEL_FILE, 'dimension': DIMENSION,
                    'license': 'MIT', 'pooling': 'attention_mask_mean_l2', 'prefixes': ['query: ', 'passage: '], 'sha256': hashes}
        (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    from app.local_embeddings import Encoder
    encoder = Encoder(directory)
    vectors = encoder.encode(['Row và Column', 'LayoutBuilder'], query=True)
    assert len(vectors) == 2 and len(vectors[0]) == DIMENSION
    print('Verified CPU inference, 384 dimensions, model code:', encoder.code)
    print('Artifacts are local and ignored by Git. Mount this directory read-only for Docker.')


if __name__ == '__main__':
    main()
