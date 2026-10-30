"""Durable queue, recovery, bounded batches, revocation and course-wide retrieval."""
from concurrent.futures import ThreadPoolExecutor
import threading
from uuid import UUID,uuid4

import pytest
from sqlalchemy import text

from test_learning import P,login
from test_rag import corpus,provider,text_pdf,student_session,workflow_state


def upload(client,corpus,code='BOOK',pages=20,kind='textbook',texts=None):
    h,run,*_=corpus
    response=client.post(f"{P}/courses/{run['course_id']}/documents",headers=h,
        data={'code':code,'title':'Giáo trình kiểm thử','document_type':kind},files={'file':('book.pdf',text_pdf(texts or ['Book cover']+['Feature normalization scales data before distance comparisons in nearest neighbors.']*(pages-1)),'application/pdf')})
    assert response.status_code==201,response.text
    return response.json()


def enqueue(client,corpus,doc):
    version=doc['versions'][0]['id']
    response=client.post(f'{P}/document-versions/{version}/rag/enable',headers=corpus[0])
    assert response.status_code==202 and response.json()['status']=='queued'
    return version,response.json()['generation_id']


def test_queue_returns_before_extraction_and_restart_resumes_embedding_checkpoint(client,corpus,database,monkeypatch):
    from app import rag
    from app.rag_worker import run_once
    doc=upload(client,corpus)
    version,generation=enqueue(client,corpus,doc)
    assert client.get(f'{P}/document-versions/{version}/chunks').json()['total']==0
    assert client.post(f'{P}/document-versions/{version}/rag/enable',headers=corpus[0]).json()['generation_id']==generation
    original=rag.get_encoder
    calls=[]
    class FailAfterCheckpoint:
        code='test-encoder'
        def encode(self,texts,query=False):
            calls.append(len(texts));assert len(texts)<=8
            if len(calls)==2:raise RuntimeError('Synthetic process interruption')
            return [[1.]+[0.]*383 for _ in texts]
    monkeypatch.setattr(rag,'get_encoder',lambda _:FailAfterCheckpoint())
    assert run_once(UUID(version))
    failed=workflow_state(client,version,drain=False)
    assert failed['status']=='failed' and failed['progress']['extracted_pages']==20
    assert failed['progress']['chunked_pages']==20 and failed['progress']['embedded_chunks']==8
    before=client.get(f'{P}/document-versions/{version}/chunks?limit=100').json()['items']
    # An abruptly lost process leaves processing+lease. A new advisory lock
    # owner reclaims immediately, without waiting for the old ten-minute lease.
    with database.begin() as db:
        db.execute(text("UPDATE rag_preparations SET status='processing',lease_id=:lease WHERE document_version_id=:id"),{'lease':uuid4(),'id':version})
    monkeypatch.setattr(rag,'get_encoder',original)
    assert run_once(UUID(version))
    ready=workflow_state(client,version,drain=False)
    assert ready['status']=='needs_review' and ready['progress']['embedded_chunks']==19
    assert ready['progress']['attempts']==2 and ready['generation_id']==generation
    after=client.get(f'{P}/document-versions/{version}/chunks?limit=100').json()['items']
    assert [(c['id'],c['source_hash'],c['revision']) for c in before]==[(c['id'],c['source_hash'],c['revision']) for c in after]


@pytest.mark.parametrize('action',['disable','delete','replace','unpublish','scope'])
def test_revocation_during_worker_batch_fences_all_late_writes(client,corpus,monkeypatch,action):
    from app import rag
    from app.rag_worker import run_once
    doc=upload(client,corpus,pages=4);version,generation=enqueue(client,corpus,doc)
    entered,release=threading.Event(),threading.Event()
    class Paused:
        code='test-encoder'
        def encode(self,texts,query=False):
            entered.set();assert release.wait(10)
            return [[1.]+[0.]*383 for _ in texts]
    monkeypatch.setattr(rag,'get_encoder',lambda _:Paused())
    h=corpus[0]
    with ThreadPoolExecutor(max_workers=1) as pool:
        job=pool.submit(run_once,UUID(version))
        try:
            assert entered.wait(10)
            other=upload(client,corpus,code='SECOND',pages=2)
            second,_=enqueue(client,corpus,other)
            assert run_once(UUID(second)) is False,'Global advisory lock permits only one CPU job'
            if action=='disable':assert client.post(f'{P}/document-versions/{version}/rag/disable',headers=h).status_code==200
            elif action=='delete':assert client.delete(f"{P}/documents/{doc['id']}",headers=h).status_code==204
            elif action=='replace':assert client.put(f"{P}/documents/{doc['id']}/file",headers=h,data={'code':'BOOK','title':'Replacement'},files={'file':('new.pdf',text_pdf(),'application/pdf')}).status_code==200
            elif action=='unpublish':assert client.patch(f"{P}/documents/{doc['id']}",headers=h,json={'status':'draft'}).status_code==200
            else:assert client.put(f'{P}/document-versions/{version}/rag/scope',headers=h,json={'expected_generation':generation,'ranges':[{'page_start':2,'page_end':2}]}).status_code==200
        finally:release.set()
        assert job.result(timeout=10)
    if action in ('delete','replace'):
        assert client.get(f'{P}/document-versions/{version}/rag').status_code==404
        assert client.get(f'{P}/document-versions/{version}/chunks').status_code==404
    else:
        state=workflow_state(client,version,drain=False)
        assert state['generation_id']!=generation
        assert state['status']==('queued' if action=='scope' else 'disabled')
        assert state['progress']['embedded_chunks']==0,'Late batch cannot commit after revocation'
    assert workflow_state(client,second,drain=False)['status']=='queued'


def test_selected_ranges_and_topic_context_do_not_lock_retrieval_to_slides(client,seeded,corpus,provider):
    from app.rag_worker import run_once
    book=upload(client,corpus,pages=3,texts=['Book cover','Feature normalization scales numerical data before distance comparisons in nearest neighbors so features share comparable units.','Unrelated historical notes outside the permitted page scope.'])
    version,generation=enqueue(client,corpus,book)
    h,run,topics,slide,_=corpus
    scope={'expected_generation':generation,'ranges':[{'page_start':2,'page_end':2,'topic_id':topics[1]['id'],'label':'Normalization chapter'}]}
    saved=client.put(f'{P}/document-versions/{version}/rag/scope',headers=h,json=scope)
    assert saved.status_code==200
    assert client.put(f'{P}/document-versions/{version}/rag/scope',headers=h,json=scope).status_code==409
    assert run_once(UUID(version))
    state=workflow_state(client,version,drain=False)
    assert state['status']=='ready' and state['progress']['selected_pages']==1
    assert client.get(f'{P}/document-versions/{version}/chunks?limit=100').json()['items'][0]['pdf_page']==2
    student,sid=student_session(client,seeded,run)
    response=client.post(f'{P}/chat-sessions/{sid}/messages',headers=student,json={'request_key':str(uuid4()),'topic_id':topics[0]['id'],'message':'Why normalize feature scales before nearest neighbors distance comparisons?'})
    assert response.status_code==201,response.text
    answer=response.json()
    assert answer['status']=='answered' and answer['citations'][0]['document_version_id']==version
    citation=answer['citations'][0]
    assert citation['pdf_page']==2 and citation['title']=='Giáo trình kiểm thử' and citation['version']==1
    assert client.get(f"{P}/course-runs/{run['id']}/document-versions/{version}/content").status_code==200
    # Source permission and library listing are independent.
    h=login(client,seeded,'teacher')
    assert client.patch(f"{P}/documents/{book['id']}",headers=h,json={'show_in_learning':False}).status_code==200
    login(client,seeded,'student')
    assert book['id'] not in [d['id'] for d in client.get(f"{P}/course-runs/{run['id']}/documents").json()['items']]
    assert client.get(f"{P}/course-runs/{run['id']}/document-versions/{version}/content").status_code==200


def test_real_worker_polling_recovers_queued_job_and_stops_cleanly(client,corpus):
    from app.rag_worker import RagWorker
    import time
    doc=upload(client,corpus,pages=4);version,_=enqueue(client,corpus,doc)
    worker=RagWorker().start()
    try:
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            state=workflow_state(client,version,drain=False)
            if state['status'] not in ('queued','processing'):break
            time.sleep(.05)
        assert state['status']=='needs_review' and state['progress']['chunked_pages']==4
    finally:worker.close()
    assert not worker.thread.is_alive()


def test_scope_metadata_acl_csrf_and_page_union(client,seeded,corpus,database):
    from app.rag_worker import run_once
    doc=upload(client,corpus,pages=5);version,generation=enqueue(client,corpus,doc)
    h,run,*_=corpus
    url=f'{P}/document-versions/{version}/rag/scope'
    body={'expected_generation':generation,'ranges':[{'page_start':2,'page_end':3},{'page_start':3,'page_end':4}]}
    assert client.put(url,json=body).status_code==403
    assert client.put(url,headers=h,json={**body,'ranges':[{'page_start':1,'page_end':6}]}).status_code==422
    other=client.post(f'{P}/courses',headers=h,json={'code':'OTHER_SCOPE','title':'Other course'}).json()
    foreign=client.post(f"{P}/courses/{other['id']}/topics",headers=h,json={'code':'X','title':'Other topic','order_index':1,'objectives':[]}).json()
    assert client.put(url,headers=h,json={**body,'ranges':[{'page_start':2,'page_end':2,'topic_id':foreign['id']}]}).status_code==422
    assert client.put(url,headers=h,json=body).status_code==200
    assert run_once(UUID(version))
    assert workflow_state(client,version,drain=False)['progress']['chunked_pages']==3
    assert client.get(f'{P}/document-versions/{version}/chunks').json()['total']==3
    student=login(client,seeded,'student')
    assert client.put(url,headers=student,json=body).status_code==403
    assert client.get(f"{P}/course-runs/{run['id']}/document-versions/{version}").status_code==200
    client.cookies.clear()
    assert client.get(f"{P}/course-runs/{run['id']}/document-versions/{version}").status_code==401
    from test_website_p0 import newcomer
    outsider,_=newcomer(client,database)
    assert client.get(f"{P}/course-runs/{run['id']}/document-versions/{version}").status_code==404


def test_chat_context_is_validated_and_part_of_idempotency(client,seeded,corpus,provider):
    h,run,topics,_,_=corpus
    other=client.post(f'{P}/courses',headers=h,json={'code':'OTHER_CHAT_CONTEXT','title':'Other'}).json()
    foreign=client.post(f"{P}/courses/{other['id']}/topics",headers=h,json={'code':'F','title':'Foreign topic','order_index':1,'objectives':[]}).json()
    student,sid=student_session(client,seeded,run)
    body={'request_key':str(uuid4()),'message':'Row and Column differ in which direction?','topic_id':topics[0]['id']}
    url=f'{P}/chat-sessions/{sid}/messages'
    assert client.post(url,headers=student,json={**body,'topic_id':foreign['id']}).status_code==422
    assert client.post(url,headers=student,json=body).status_code==201
    assert client.post(url,headers=student,json=body).status_code==200
    assert client.post(url,headers=student,json={**body,'topic_id':topics[1]['id']}).status_code==409


def test_document_kind_does_not_promote_unrelated_textbook(monkeypatch):
    from app import rag_retrieval
    class Encoder:
        code='fixture'
        def encode(self,*_,**__):return [[1.]+[0.]*383]
    monkeypatch.setattr(rag_retrieval,'get_encoder',lambda _:Encoder())
    common={'embedding':[1.]+[0.]*383,'embedding_code':'fixture','flags':[],'extraction_method':'pypdf','pdf_page':2,'chunk_index':0,'topic_ids':[]}
    sources=[common|{'id':'a','text':'Unrelated historical account of botanical classifications.','document_type':'textbook'},common|{'id':'b','text':'Feature normalization scales data for nearest neighbors distance comparisons.','document_type':'lecture'}]
    assert rag_retrieval.retrieve_hybrid(None,'Why normalize feature data for nearest neighbors distance comparisons?',iter(sources))[0]['id']=='b'
