from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from conftest import ORIGIN
from test_learning import P, begin, event, login, make_quiz, pdf_bytes, private_pdf_storage, send_events, setup_content


def publish(client, headers, course_id, **changes):
    draft = dict(title='Học máy căn bản', summary='Làm quen mô hình học máy', description='Học máy và đánh giá mô hình từ dữ liệu.', category_code='data-science', level='beginner', objectives=['Hiểu mô hình'], prerequisites=[], outline=['Dữ liệu và mô hình'], material_titles=['Tài liệu học máy'])
    draft.update(changes)
    result = client.patch(f'{P}/teaching/courses/{course_id}/publication', headers=headers, json=draft)
    assert result.status_code == 200, result.text
    result = client.post(f'{P}/teaching/courses/{course_id}/publish', headers=headers)
    assert result.status_code == 200, result.text
    return result.json()


def configure(client, headers, run, mode='open', **changes):
    current = client.get(f"{P}/teaching/runs/{run['id']}/admissions").json()
    body = dict(enrollment_mode=mode, listed=True, opens_at=None, closes_at=None, capacity=None, expected_revision=current['admissions_revision'])
    body.update(changes)
    response = client.patch(f"{P}/teaching/runs/{run['id']}/admissions", headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def newcomer(client, database, email=None):
    from app.models import User
    from app.security import hash_password
    email = email or f'{uuid4().hex}@example.com'
    password = 'Website-fixture-password-123'
    with Session(database) as db:
        db.add(User(email=email,password_hash=hash_password(password),display_name='Sinh viên website',role='student',is_active=True))
        db.commit()
    client.cookies.clear()
    result = client.post(f'{P}/auth/login',headers={'Origin':ORIGIN},json={'email':email,'password':password})
    assert result.status_code == 200
    return {'Origin':ORIGIN,'X-CSRF-Token':result.json()['csrf_token']}, dict(client.cookies)


def setup_public(client, seeded, mode='open'):
    headers, run, topics, document = setup_content(client, seeded)
    publication = publish(client,headers,run['course_id'])
    settings = configure(client,headers,run,mode)
    return headers,run,topics,document,publication,settings


def test_catalog_hidden_defaults_and_public_whitelist(client,seeded):
    headers,run,topics,document = setup_content(client,seeded)
    owner = client.get(f"{P}/teaching/courses/{run['course_id']}/publication").json()
    assert owner['status']=='hidden'
    admission = client.get(f"{P}/teaching/runs/{run['id']}/admissions").json()
    assert admission['enrollment_mode']=='invite_only' and admission['listed'] is False
    client.cookies.clear()
    assert client.get(f'{P}/catalog/courses').json()['total']==0
    assert client.get(f"{P}/catalog/courses/{owner['slug']}").status_code==404
    headers=login(client,seeded,'teacher')
    published=publish(client,headers,run['course_id'])
    configure(client,headers,run)
    client.cookies.clear()
    detail=client.get(f"{P}/catalog/courses/{published['slug']}")
    assert detail.status_code==200 and detail.json()['runs'][0]['id']==run['id']
    content=detail.text
    for forbidden in ('storage_key','password_hash','student_email','correct_option','csrf_token','owner_teacher_id',document['versions'][0]['id']):
        assert forbidden not in content
    for path in (f"/document-versions/{document['versions'][0]['id']}/content",f"/course-runs/{run['id']}/topics",'/courses','/me/profile'):
        assert client.get(P+path).status_code==401


def test_catalog_search_filters_snapshot_and_stable_pagination(client,seeded):
    headers,run,_,_,publication,_=setup_public(client,seeded)
    for q in ('Học máy','hoc may','HỌC MÁY','MOBILE_MULTIPLATFORM'):
        assert client.get(f'{P}/catalog/courses',params={'q':q}).json()['total']==1
    assert client.get(f'{P}/catalog/courses',params={'q':'%'}).json()['total']==0
    assert client.get(f'{P}/catalog/courses',params={'q':"' OR 1=1 --"}).json()['total']==0
    assert client.get(f'{P}/catalog/courses?sort=drop-table').status_code==422
    assert client.get(f'{P}/catalog/courses?limit=1000').status_code==422
    assert client.get(f'{P}/catalog/courses?category=general').json()['total']==0
    assert client.get(f'{P}/catalog/courses?level=advanced').json()['total']==0
    second=client.post(f'{P}/courses',headers=headers,json={'code':'SECOND_WEB','title':'Khác'}).json()
    publish(client,headers,second['id'],title='Học máy nâng cao')
    first=client.get(f'{P}/catalog/courses?sort=title&limit=1').json()
    next_page=client.get(f'{P}/catalog/courses?sort=title&limit=1&offset=1').json()
    assert first['total']==2 and first['items'][0]['slug']!=next_page['items'][0]['slug']
    draft=publication['draft'];draft['title']='Bản sửa chưa công bố'
    assert client.patch(f"{P}/teaching/courses/{run['course_id']}/publication",headers=headers,json=draft).status_code==200
    assert client.get(f"{P}/catalog/courses/{publication['slug']}").json()['title']=='Học máy căn bản'
    assert client.get(f'{P}/catalog/courses?availability=accepting').json()['total']==1


def test_hidden_does_not_revoke_membership_and_synthetic_never_listed(client,seeded,database):
    from app.models import CourseRun
    headers,run,_,_,publication,_=setup_public(client,seeded)
    assert client.post(f"{P}/teaching/courses/{run['course_id']}/hide",headers=headers).status_code==200
    login(client,seeded,'student')
    assert client.get(f"{P}/course-runs/{run['id']}/topics").status_code==200
    assert client.get(f"{P}/catalog/courses/{publication['slug']}").status_code==404
    headers=login(client,seeded,'teacher');publish(client,headers,run['course_id'])
    with Session(database) as db:
        row=db.get(CourseRun,UUID(run['id']));row.data_origin='synthetic';db.commit()
    assert client.get(f"{P}/catalog/courses/{publication['slug']}").json()['runs']==[]
    body=dict(enrollment_mode='open',listed=True,expected_revision=2)
    assert client.patch(f"{P}/teaching/runs/{run['id']}/admissions",headers=headers,json=body).status_code==409


def test_publication_admissions_owner_and_csrf(client,seeded,database):
    headers,run,_,_,publication,settings=setup_public(client,seeded)
    assert client.post(f"{P}/teaching/courses/{run['course_id']}/hide",headers={'Origin':ORIGIN}).status_code==403
    login(client,seeded,'student')
    assert client.get(f"{P}/teaching/courses/{run['course_id']}/publication").status_code==403
    with database.begin() as db:
        db.execute(text("UPDATE users SET role='teacher' WHERE email='student@example.com'"))
    other=login(client,seeded,'student')
    for path in (f"/teaching/courses/{run['course_id']}/publication",f"/teaching/runs/{run['id']}/admissions",f"/teaching/runs/{run['id']}/requests"):
        assert client.get(P+path).status_code==404
    assert client.post(f"{P}/teaching/courses/{run['course_id']}/hide",headers=other).status_code==404


def test_open_retry_inactive_and_policy_revision(client,seeded,database):
    from app.models import Enrollment
    headers,run,_,_,_,settings=setup_public(client,seeded)
    student_headers,_=newcomer(client,database)
    url=f"{P}/course-runs/{run['id']}/join"
    assert client.post(url,headers={'Origin':ORIGIN},json={'expected_revision':settings['admissions_revision']}).status_code==403
    assert client.post(url,headers=student_headers,json={'expected_revision':1}).status_code==409
    first=client.post(url,headers=student_headers,json={'expected_revision':settings['admissions_revision']})
    assert first.status_code==201
    second=client.post(url,headers=student_headers,json={'expected_revision':settings['admissions_revision']})
    assert second.status_code==200 and first.json()['id']==second.json()['id']
    with Session(database) as db:
        enrollment=db.get(Enrollment,UUID(first.json()['id']));enrollment.status='inactive';db.commit()
    assert client.post(url,headers=student_headers,json={'expected_revision':settings['admissions_revision']}).json()['error']['code']=='ENROLLMENT_INACTIVE'
    assert client.get(f"{P}/course-runs/{run['id']}/topics").status_code==404


def test_approval_cancel_decision_and_manual_email(client,seeded,database):
    from app.website_models import EnrollmentRequest
    headers,run,_,_,_,settings=setup_public(client,seeded,'approval')
    student_headers,student_cookies=newcomer(client,database,'approval.web@example.com')
    url=f"{P}/course-runs/{run['id']}/enrollment-requests"
    body={'expected_revision':settings['admissions_revision']}
    first=client.post(url,headers=student_headers,json=body)
    assert first.status_code==201
    request=first.json()
    assert client.post(url,headers=student_headers,json=body).json()['id']==request['id']
    assert client.get(f'{P}/me/enrollment-requests').json()['total']==1
    assert client.post(f"{P}/me/enrollment-requests/{request['id']}/cancel",headers=student_headers).json()['status']=='cancelled'
    request=client.post(url,headers=student_headers,json=body).json()
    headers=login(client,seeded,'teacher')
    decision=f"{P}/teaching/requests/{request['id']}/decision"
    approved=client.post(decision,headers=headers,json={'action':'approve','reason':'Đã kiểm tra'})
    assert approved.status_code==200 and approved.json()['status']=='approved'
    assert client.post(decision,headers=headers,json={'action':'approve'}).status_code==200
    assert client.post(decision,headers=headers,json={'action':'reject'}).status_code==409
    with Session(database) as db:
        row=db.get(EnrollmentRequest,UUID(request['id']));assert row.decided_by and row.decided_at
    client.cookies.clear();client.cookies.update(student_cookies)
    assert client.get(f"{P}/course-runs/{run['id']}/topics").status_code==200


@pytest.mark.parametrize('mode',['open','approval'])
def test_last_seat_is_serialized_and_pending_does_not_reserve(client,seeded,database,mode):
    from app.main import app
    from app.models import Enrollment
    headers,run,_,_,_,_=setup_public(client,seeded,mode)
    settings=configure(client,headers,run,mode,capacity=2) # One existing seeded enrollment.
    calls=[]
    for _ in range(2):
        h,c=newcomer(client,database)
        if mode=='approval':
            request=client.post(f"{P}/course-runs/{run['id']}/enrollment-requests",headers=h,json={'expected_revision':settings['admissions_revision']}).json()
            calls.append((request['id'],None,None))
        else:
            calls.append((None,h,c))
    owner_headers=login(client,seeded,'teacher');owner_cookies=dict(client.cookies)
    def compete(call):
        request_id,h,cookies=call
        with TestClient(app) as worker:
            worker.cookies.update(cookies or owner_cookies)
            if request_id:
                return worker.post(f'{P}/teaching/requests/{request_id}/decision',headers=owner_headers,json={'action':'approve'}).status_code
            return worker.post(f"{P}/course-runs/{run['id']}/join",headers=h,json={'expected_revision':settings['admissions_revision']}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses=list(pool.map(compete,calls))
    assert sorted(statuses)==([200,409] if mode=='approval' else [201,409])
    with Session(database) as db:
        assert db.scalar(select(func.count()).select_from(Enrollment).where(Enrollment.course_run_id==UUID(run['id']),Enrollment.status=='active'))==2


def test_approval_window_checked_at_decision_and_owner_other_denied(client,seeded,database):
    from app.security import utcnow
    headers,run,_,_,_,settings=setup_public(client,seeded,'approval')
    h,cookies=newcomer(client,database)
    request=client.post(f"{P}/course-runs/{run['id']}/enrollment-requests",headers=h,json={'expected_revision':settings['admissions_revision']}).json()
    with database.begin() as db:
        db.execute(text('UPDATE course_runs SET closes_at=:time WHERE id=:id'),{'time':utcnow()-timedelta(seconds=1),'id':run['id']})
    headers=login(client,seeded,'teacher')
    assert client.post(f"{P}/teaching/requests/{request['id']}/decision",headers=headers,json={'action':'approve'}).status_code==409
    assert client.post(f"{P}/teaching/requests/{request['id']}/decision",headers=headers,json={'action':'reject','reason':'Hết thời gian'}).status_code==200
    assert client.get(f"{P}/teaching/runs/{run['id']}/requests?status=rejected").json()['total']==1


def test_profile_whitelist_password_revokes_all_sessions(client,seeded,database):
    from app.accounts import _password_hits
    h=login(client,seeded,'student');cookies=dict(client.cookies)
    assert client.patch(f'{P}/me/profile',headers=h,json={'display_name':'Tên mới','bio':'Riêng tư','role':'teacher'}).status_code==422
    assert client.patch(f'{P}/me/profile',headers=h,json={'display_name':'Tên mới','bio':'Riêng tư','email':'x@example.com'}).status_code==422
    result=client.patch(f'{P}/me/profile',headers=h,json={'display_name':'Tên mới','bio':'Riêng tư'})
    assert result.status_code==200 and result.json()['role']=='student'
    second=login(client,seeded,'student')
    body={'current_password':'wrong','new_password':'Changed-password-123'}
    assert client.post(f'{P}/me/password',headers={'Origin':ORIGIN},json=body).status_code==403
    assert client.post(f'{P}/me/password',headers=second,json=body).status_code==422
    body['current_password']=seeded['student']
    assert client.post(f'{P}/me/password',headers=second,json=body).status_code==204
    assert client.get(f'{P}/auth/me').status_code==401
    client.cookies.update(cookies)
    assert client.get(f'{P}/auth/me').status_code==401
    client.cookies.clear()
    assert client.post(f'{P}/auth/login',headers={'Origin':ORIGIN},json={'email':'student@example.com','password':seeded['student']}).status_code==401
    assert client.post(f'{P}/auth/login',headers={'Origin':ORIGIN},json={'email':'student@example.com','password':'Changed-password-123'}).status_code==200


def test_password_rate_limit_and_cross_role_overview(client,seeded):
    h=login(client,seeded,'student')
    for _ in range(5):
        assert client.post(f'{P}/me/password',headers=h,json={'current_password':'wrong','new_password':'New-password-123'}).status_code==422
    assert client.post(f'{P}/me/password',headers=h,json={'current_password':'wrong','new_password':'New-password-123'}).status_code==429
    assert client.get(f'{P}/teaching/overview').status_code==403
    login(client,seeded,'teacher')
    assert client.get(f'{P}/me/overview').status_code==403


def test_resume_and_overview_do_not_create_events_and_fallback_after_delete(client,seeded):
    headers,run,topics,doc=setup_content(client,seeded)
    student_headers=login(client,seeded,'student')
    body={'run_id':run['id'],'topic_id':topics[0]['id'],'document_version_id':doc['versions'][0]['id'],'view':'pdf','page':2}
    assert client.put(f'{P}/me/resume',headers=student_headers,json=body).status_code==200
    assert client.get(f'{P}/me/resume').json()['resume']['page']==2
    overview=client.get(f'{P}/me/overview').json()
    assert overview['courses'][0]['progress']['percent'] is None
    assert client.get(f"{P}/course-runs/{run['id']}/events").json()['total']==0
    body['page']=500
    assert client.put(f'{P}/me/resume',headers=student_headers,json=body).status_code==422
    headers=login(client,seeded,'teacher')
    assert client.delete(f"{P}/documents/{doc['id']}",headers=headers).status_code==204
    login(client,seeded,'student')
    resume=client.get(f'{P}/me/resume').json()['resume']
    assert resume['view']=='topic' and resume['document_version_id'] is None and resume['notice']
    assert client.get(f"{P}/course-runs/{run['id']}/events").json()['total']==0


@pytest.mark.parametrize('boundary,expected', [('future',409),('expired',409),('closed',409),('unlisted',404),('hidden',404),('invite_only',409)])
def test_join_rechecks_every_admission_boundary(client,seeded,database,boundary,expected):
    from app.models import CourseRun
    from app.security import utcnow
    from app.website_models import CoursePublication
    _,run,_,_,_,settings=setup_public(client,seeded)
    with Session(database) as db:
        row=db.get(CourseRun,UUID(run['id']))
        if boundary=='future': row.opens_at=utcnow()+timedelta(days=1)
        if boundary=='expired': row.closes_at=utcnow()-timedelta(seconds=1)
        if boundary=='closed': row.status='closed'
        if boundary=='unlisted': row.listed=False
        if boundary=='invite_only': row.enrollment_mode='invite_only'
        if boundary=='hidden': db.get(CoursePublication,UUID(run['course_id'])).status='hidden'
        db.commit()
    h,_=newcomer(client,database)
    assert client.post(f"{P}/course-runs/{run['id']}/join",headers=h,json={'expected_revision':settings['admissions_revision']}).status_code==expected
    assert client.get(f'{P}/me/courses').json()['total']==0


def test_request_ownership_cancel_and_decision_csrf(client,seeded,database):
    _,run,_,_,_,settings=setup_public(client,seeded,'approval')
    h,cookies=newcomer(client,database)
    request=client.post(f"{P}/course-runs/{run['id']}/enrollment-requests",headers=h,json={'expected_revision':settings['admissions_revision']}).json()
    other,_=newcomer(client,database)
    assert client.post(f"{P}/me/enrollment-requests/{request['id']}/cancel",headers=other).status_code==404
    assert client.get(f'{P}/me/enrollment-requests').json()['total']==0
    with database.begin() as db:
        db.execute(text("UPDATE users SET role='teacher' WHERE email='student@example.com'"))
    other_teacher=login(client,seeded,'student')
    decision=f"{P}/teaching/requests/{request['id']}/decision"
    assert client.post(decision,headers=other_teacher,json={'action':'approve'}).status_code==404
    owner=login(client,seeded,'teacher')
    assert client.post(decision,headers={'Origin':ORIGIN},json={'action':'approve'}).status_code==403
    assert client.post(decision,headers=owner,json={'action':'reject','reason':'Chưa đáp ứng điều kiện'}).status_code==200
    client.cookies.clear();client.cookies.update(cookies)
    assert client.post(f"{P}/me/enrollment-requests/{request['id']}/cancel",headers=h).status_code==409


def test_manual_email_and_reactivation_share_capacity_and_request_audit(client,seeded,database):
    _,run,_,_,_,settings=setup_public(client,seeded,'approval')
    h,_=newcomer(client,database,'manual.web@example.com')
    request=client.post(f"{P}/course-runs/{run['id']}/enrollment-requests",headers=h,json={'expected_revision':settings['admissions_revision']}).json()
    newcomer(client,database,'capacity.web@example.com')
    owner=login(client,seeded,'teacher')
    configure(client,owner,run,'approval',capacity=2)
    url=f"{P}/course-runs/{run['id']}/enrollments"
    manual=client.post(url,headers=owner,json={'student_email':'manual.web@example.com'})
    assert manual.status_code==201
    assert client.get(f"{P}/teaching/runs/{run['id']}/requests?status=approved").json()['items'][0]['id']==request['id']
    assert client.post(url,headers=owner,json={'student_email':'manual.web@example.com'}).json()['id']==manual.json()['id']
    assert client.post(url,headers=owner,json={'student_email':'capacity.web@example.com'}).status_code==409
    assert client.patch(f"{P}/enrollments/{manual.json()['id']}",headers=owner,json={'status':'inactive'}).status_code==200
    assert client.post(url,headers=owner,json={'student_email':'manual.web@example.com'}).status_code==409
    assert client.post(url,headers=owner,json={'student_email':'capacity.web@example.com'}).status_code==201
    assert client.patch(f"{P}/enrollments/{manual.json()['id']}",headers=owner,json={'status':'active'}).status_code==409
    current=client.get(f"{P}/teaching/runs/{run['id']}/admissions").json()
    body={k:current[k] for k in ('enrollment_mode','listed','opens_at','closes_at','capacity')}
    body.update(capacity=1,expected_revision=current['admissions_revision'])
    assert client.patch(f"{P}/teaching/runs/{run['id']}/admissions",headers=owner,json=body).status_code==409


def test_resume_rejects_foreign_topic_and_inactive_membership(client,seeded,database):
    from app.models import Enrollment
    owner,run,topics,_=setup_content(client,seeded)
    foreign=client.post(f'{P}/courses',headers=owner,json={'code':'OTHER_RESUME','title':'Học phần khác'}).json()
    foreign_topic=client.post(f"{P}/courses/{foreign['id']}/topics",headers=owner,json={'code':'OTHER','title':'Chủ đề khác','order_index':1,'objectives':[]}).json()
    h=login(client,seeded,'student')
    body={'run_id':run['id'],'topic_id':foreign_topic['id'],'view':'topic','page':1}
    assert client.put(f'{P}/me/resume',headers=h,json=body).status_code==422
    body['topic_id']=topics[0]['id']
    assert client.put(f'{P}/me/resume',headers=h,json=body).status_code==200
    with Session(database) as db:
        row=db.scalar(select(Enrollment).where(Enrollment.course_run_id==UUID(run['id'])))
        row.status='inactive';db.commit()
    assert client.put(f'{P}/me/resume',headers=h,json=body).status_code==404
    assert client.get(f'{P}/me/resume').json()['resume'] is None
    assert client.get(f"{P}/me/resume?run_id={run['id']}").status_code==404


def test_overview_progress_uses_current_published_quiz_without_path_writes(client,seeded,database):
    owner,run,topics,doc=setup_content(client,seeded)
    quiz=make_quiz(client,owner,topics[0],doc['versions'][0]['id'])
    h=login(client,seeded,'student')
    attempt=begin(client,h,run,topics[0],quiz).json()
    url=f"{P}/attempts/{attempt['id']}"
    answers=[{'quiz_version_item_id':item['quiz_version_item_id'],'selected_option':'B'} for item in attempt['items']]
    assert client.put(url+'/answers',headers=h,json={'expected_revision':0,'answers':answers}).status_code==200
    assert client.post(url+'/submit',headers=h,json={'expected_revision':1}).status_code==200
    with database.connect() as db:
        counts_before={table:db.execute(text('SELECT count(*) FROM '+table)).scalar() for table in ('learning_events','learning_paths')}
    progress=client.get(f'{P}/me/overview').json()['courses'][0]['progress']
    assert progress=={'mastered':1,'available':1,'percent':100.0}
    owner=login(client,seeded,'teacher')
    make_quiz(client,owner,topics[0],doc['versions'][0]['id'])
    login(client,seeded,'student')
    progress=client.get(f'{P}/me/overview').json()['courses'][0]['progress']
    assert progress=={'mastered':0,'available':1,'percent':0.0}
    with database.connect() as db:
        assert all(db.execute(text('SELECT count(*) FROM '+table)).scalar()==count for table,count in counts_before.items())
