"""Frozen multilingual E5 ONNX inference on CPU. No training or embedding API."""
import hashlib
import json
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.errors import ApiError

REPO = 'intfloat/multilingual-e5-small'
REVISION = '614241f622f53c4eeff9890bdc4f31cfecc418b3'
MODEL_FILE = 'onnx/model_qint8_avx512_vnni.onnx'
DIMENSION = 384


def unavailable():
    return ApiError(503, 'EMBEDDING_UNAVAILABLE', 'Model/vector embedding local chưa sẵn sàng. Chuẩn bị model và lập chỉ mục các đoạn đã duyệt trước khi hỏi.')


class Encoder:
    def __init__(self, directory: Path):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        if manifest['repo'] != REPO or manifest['revision'] != REVISION or manifest['dimension'] != DIMENSION:
            raise ValueError('Unexpected embedding model')
        for name in ('model.onnx', 'tokenizer.json'):
            if hashlib.sha256((directory / name).read_bytes()).hexdigest() != manifest['sha256'][name]:
                raise ValueError('Embedding artifact hash mismatch')
        self.code = 'multilingual-e5-small-qint8:' + hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:24]
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2; options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(directory / 'model.onnx'), sess_options=options, providers=['CPUExecutionProvider'])
        self.tokenizer = Tokenizer.from_file(str(directory / 'tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=512)
        self.tokenizer.enable_padding(pad_id=1, pad_token='<pad>')
        self.lock = threading.Lock()

    def encode(self, texts, query=False):
        output = []
        prefix = 'query: ' if query else 'passage: '
        with self.lock:
            for start in range(0, len(texts), 8):
                encoded = self.tokenizer.encode_batch([prefix + t for t in texts[start:start + 8]])
                ids = np.asarray([e.ids for e in encoded], dtype=np.int64)
                mask = np.asarray([e.attention_mask for e in encoded], dtype=np.int64)
                values = {'input_ids': ids, 'attention_mask': mask, 'token_type_ids': np.zeros_like(ids)}
                feed = {v.name: values[v.name] for v in self.session.get_inputs()}
                hidden = self.session.run(None, feed)[0]
                weighted = hidden * mask[:, :, None]
                pooled = weighted.sum(axis=1) / np.maximum(mask.sum(axis=1)[:, None], 1)
                norms = np.linalg.norm(pooled, axis=1, keepdims=True)
                vectors = pooled / np.maximum(norms, 1e-12)
                if vectors.shape != (len(encoded), DIMENSION) or not np.isfinite(vectors).all():
                    raise ValueError('Invalid embeddings')
                output.extend(vectors.tolist())
        return output


@lru_cache(maxsize=2)
def _load(path, manifest_stamp):
    return Encoder(Path(path))


def get_encoder(settings):
    try:
        directory = settings.embedding_model_path.resolve()
        return _load(str(directory), (directory / 'manifest.json').stat().st_mtime_ns)
    except Exception:
        raise unavailable() from None
