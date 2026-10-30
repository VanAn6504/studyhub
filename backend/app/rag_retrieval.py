"""Local BM25 baseline with accent folding and explicit Vietnamese query expansion."""
import math
import re
import unicodedata
from collections import Counter

import numpy as np

from app.local_embeddings import get_encoder, unavailable

STOP = set('la gi co va cua tu trong voi cho nao the nhu nhung mot cac ve hay toi ban xin nay de khi ra duoc khong thi at the a an in of to is are how what where and or from this do does please'.split())
EXPANSIONS = {
    'thu muc': 'directory folder', 'vai tro': 'purpose contains directory',
    'khac nhau': 'horizontal vertical', 'kich thuoc': 'size constraints dimensions',
    'ngang': 'horizontal', 'doc': 'vertical', 'cha': 'parent',
}
TECHNICAL = set('lib row column layoutbuilder sqlite methodchannel isolate listview gridview'.split())


def normalize(value):
    value = unicodedata.normalize('NFKD', value.lower().replace('đ', 'd'))
    return ''.join(c for c in value if not unicodedata.combining(c))


def tokens(value):
    return [t for t in re.findall(r'[a-z0-9_]+', normalize(value)) if len(t) > 1 and t not in STOP and not t.isdigit()]


def retrieve(question, sources):
    """Returns at most four reviewed page chunks. Never queries question/quiz tables."""
    normalized = normalize(question)
    original = set(tokens(question))
    expanded = normalized
    for phrase, words in EXPANSIONS.items():
        if phrase in normalized:
            expanded += ' ' + words
    query = set(tokens(expanded))
    # Named APIs/identifiers must occur in the returned evidence, not just an alias.
    anchors = original & TECHNICAL
    anchors.update(normalize(t) for t in re.findall(r'\b[A-Za-z]+(?:[A-Z][a-z]+)+\b', question))
    if not query or not sources:
        return []
    counts = [Counter(tokens(s['text'])) for s in sources]
    lengths = [sum(c.values()) for c in counts]
    average = sum(lengths) / max(1, len(lengths)) or 1
    df = Counter(t for c in counts for t in c)
    results = []
    for source, count, length in zip(sources, counts, lengths):
        overlap = query & count.keys()
        if not overlap:
            continue
        # Code copied from an image has no evidence until a manual transcription is reviewed.
        if ('ma nguon' in normalized or 'code' in original) and 'contains_images' in source['flags'] and source['extraction_method'] != 'manual':
            continue
        score = sum(math.log(1 + (len(sources) - df[t] + .5) / (df[t] + .5)) *
                    count[t] * 2.2 / (count[t] + 1.2 * (.25 + .75 * length / average)) *
                    (3 if t in anchors else 1) for t in overlap)
        results.append((score, source))
    results.sort(key=lambda row: (-row[0], row[1]['pdf_page'], row[1]['chunk_index'], row[1]['id']))
    selected = [source for _, source in results[:4]]
    if anchors and not anchors.issubset(set(t for s in selected for t in tokens(s['text']))):
        return []
    return selected


def retrieve_hybrid(settings, question, sources, topic_id=None):
    """Scan authorized sources in bounded batches, then BM25+cosine RRF.

    Only128 candidate dictionaries/vectors remain in memory; a textbook's
    relevance can compete with slides anywhere in the course. Topic/type are
    small tie signals only after lexical overlap and semantic sufficiency.
    """
    import heapq
    from itertools import chain, islice
    iterator=iter(sources)
    first=next(iterator,None)
    if first is None:return []
    iterator=chain([first],iterator)
    normalized,original=normalize(question),set(tokens(question))
    if not original:return []
    anchors=original & TECHNICAL
    anchors.update(normalize(t) for t in re.findall(r'\b[A-Za-z]+(?:[A-Z][a-z]+)+\b',question))
    encoder=get_encoder(settings)
    try:
        vector=np.asarray(encoder.encode([question],query=True)[0],dtype=np.float32)
        if vector.shape!=(384,) or not np.isfinite(vector).all():raise ValueError('Invalid query embedding')
    except Exception:raise unavailable() from None
    semantic_heap,lexical_heap=[],[]
    while batch:=list(islice(iterator,128)):
        batch=[s for s in batch if not (('ma nguon' in normalized or 'code' in original) and 'contains_images' in s['flags'] and s['extraction_method']!='manual')]
        if anchors:batch=[s for s in batch if anchors.intersection(tokens(s['text']))]
        if not batch:continue
        if any(s['embedding_code']!=encoder.code or not s['embedding'] for s in batch):raise unavailable()
        try:
            matrix=np.asarray([s['embedding'] for s in batch],dtype=np.float32)
            if matrix.shape!=(len(batch),384) or not np.isfinite(matrix).all():raise ValueError('Invalid passage embedding')
            similarities=matrix@vector
        except Exception:raise unavailable() from None
        for source,similarity in zip(batch,similarities):
            similarity=float(similarity)
            if similarity<.72:continue
            terms=Counter(tokens(source['text']))
            lexical=sum(min(terms[t],3)*(3 if t in anchors else 1) for t in original)
            for heap,key in ((semantic_heap,similarity),(lexical_heap,lexical)):
                entry=(key,source['id'],similarity,source)
                if len(heap)<64:heapq.heappush(heap,entry)
                elif entry[:2]>heap[0][:2]:heapq.heapreplace(heap,entry)
    by_id={entry[1]:(entry[2],entry[3]) for entry in semantic_heap+lexical_heap}
    if not by_id:return []
    semantic=sorted(by_id.values(),key=lambda row:(-row[0],row[1]['id']))
    candidates=[source for _,source in semantic]
    lexical=retrieve(question,candidates)
    semantic_rank={s['id']:i for i,s in enumerate(candidates)}
    lexical_rank={s['id']:i for i,s in enumerate(lexical)}
    def score(source):
        value=1/(60+semantic_rank[source['id']])
        if source['id'] in lexical_rank:value+=1/(60+lexical_rank[source['id']])
        if original.intersection(tokens(source['text'])):
            if topic_id and str(topic_id) in source.get('topic_ids',[]):value*=1.04
            if source.get('document_type')=='textbook':value*=1.01
        return value
    selected=sorted(candidates,key=lambda source:(-score(source),source['id']))[:4]
    if anchors and not anchors.issubset(set(t for source in selected for t in tokens(source['text']))):return []
    return selected
