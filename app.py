import streamlit as st
import pandas as pd
import database as db

st.set_page_config(page_title='IELTS Zone', page_icon='🎓', layout='wide')
db.setup()
st.title('IELTS ZONE')
st.caption('Student Enrollment Management System')
page = st.sidebar.radio('Navigation', [
    'Dashboard', 'Student Registration', 'Level Assessment',
    'Group Allocation', 'Trial Lessons', 'Payments'
])

if page == 'Dashboard':
    st.header('Dashboard')
    all_students = db.students()
    c1, c2, c3 = st.columns(3)
    c1.metric('Applications', len(all_students))
    c2.metric('Waiting List', sum(s[6] == 'Waiting List' for s in all_students))
    c3.metric('Groups Assigned', sum(s[6] in (
    'Group Assigned', 'Trial Scheduled', 'Trial Missed',
    'Trial Completed', 'Ready for Payment', 'Declined', 'Enrolled'
) for s in all_students))
    st.info('Use the sidebar to manage the enrollment process.')

elif page == 'Student Registration':
    st.header('Student Registration')
    with st.form('register', clear_on_submit=True):
        name = st.text_input('Full Name *')
        phone = st.text_input('Phone Number *')
        email = st.text_input('Email')
        branch = st.selectbox('Preferred Branch *', ['Chilonzor', 'Yunusobod', 'Sergeli'])
        certificate = st.radio('Has IELTS/CEFR certificate?', ['No', 'Yes'])
        if st.form_submit_button('Save Student'):
            if not name.strip() or not phone.strip():
                st.error('Name and phone are required.')
            else:
                db.register(name.strip(), phone.strip(), email.strip(), branch, certificate)
                st.success('Student saved.')
    st.subheader('Registered Students')
    st.dataframe(pd.DataFrame(db.students(), columns=[
        'ID', 'Name', 'Phone', 'Email', 'Branch', 'Certificate', 'Status'
    ]), hide_index=True, use_container_width=True)

elif page == 'Level Assessment':
    st.header('Level Assessment')
    choices = [s for s in db.students() if s[6] in ('Pending Assessment', 'Ready for Group Allocation')]
    if not choices:
        st.info('No students currently need assessment.')
    else:
        options = {f'{s[0]} - {s[1]}': s for s in choices}
        student = options[st.selectbox('Select Student', list(options))]
        methods = ['Certificate', 'Placement Test'] if student[5] == 'Yes' else ['Placement Test']
        method = st.radio('Assessment Method', methods)
        with st.form('assessment'):
            cert_type = cert_score = verification = test_date = written = speaking = None
            if method == 'Certificate':
                cert_type = st.selectbox('Certificate Type', ['IELTS', 'CEFR'])
                cert_score = st.text_input('Certificate Score / Level')
                verification = st.selectbox('Verification Status', ['Pending', 'Verified', 'Invalid'])
            else:
                test_date = st.date_input('Test Date')
                test_status = st.selectbox('Test Status', ['Scheduled', 'Completed'])
                written = st.number_input('Written Score', min_value=0, max_value=100)
                speaking = st.number_input('Speaking Score', min_value=0, max_value=100)
            level = st.selectbox('Determined English Level', ['Select Level', 'A1', 'A2', 'B1', 'B2', 'C1', 'C2'])
            if st.form_submit_button('Save Assessment'):
                if method == 'Certificate' and (verification != 'Verified' or not cert_score.strip()):
                    st.error('A verified certificate and its score are required.')
                elif method == 'Placement Test' and test_status != 'Completed':
                    st.error('The test must be completed first.')
                elif level == 'Select Level':
                    st.error('Select an English level.')
                else:
                    try:
                        db.save_assessment(student[0], method, cert_type, cert_score,
                                           verification, str(test_date) if test_date else None,
                                           written, speaking, level)
                        st.success('Assessment saved successfully.')
                    except ValueError as error:
                        st.error(str(error))
    st.subheader('Completed Assessments')
    st.dataframe(pd.DataFrame(db.assessments(), columns=[
        'Assessment ID', 'Student', 'Method', 'Level'
    ]), hide_index=True, use_container_width=True)

elif page == 'Group Allocation':
    st.header('Group Allocation and Waiting List')
    if 'message' in st.session_state:
        st.success(st.session_state.pop('message'))
    choices = db.eligible_students()
    if not choices:
        st.info('No students currently need group allocation. Assigned and waiting students are listed below.')
    else:
        options = {f'{s[0]} - {s[1]}': s for s in choices}
        student = options[st.selectbox('Select Student', list(options))]
        st.write('English level:', student[3], '| Preferred branch:', student[2])
        groups = db.matching_groups(student[3], student[2])
        if not groups:
            st.warning('No matching group. Check the student level and branch.')
        else:
            st.dataframe(pd.DataFrame([
                (g[1], g[2], g[3], g[4], g[3]-g[4]) for g in groups
            ], columns=['Group', 'Schedule', 'Capacity', 'Occupied', 'Spaces Left']),
                hide_index=True, use_container_width=True)
            options = {g[1]: g for g in groups}
            group = options[st.selectbox('Select Group', list(options))]
            if group[4] < group[3]:
                st.success('Places available')
                if st.button('Assign Group'):
                    try:
                        st.session_state['message'] = db.allocate(student[0], group[0])
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
            else:
                st.warning('Group full')
                date = st.date_input('Waiting List Date')
                if st.button('Add to Waiting List'):
                    try:
                        st.session_state['message'] = db.allocate(student[0], group[0], str(date))
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
    st.subheader('Assigned Students')
    st.dataframe(pd.DataFrame(db.assigned_students(), columns=['Student', 'Group', 'Status']),
                 hide_index=True, use_container_width=True)
    st.subheader('Waiting List')
    waiting = db.waiting_students()
    st.dataframe(pd.DataFrame([w[:4] for w in waiting], columns=[
        'Student ID', 'Student', 'Group', 'Waiting Since'
    ]), hide_index=True, use_container_width=True)
    if waiting:
        st.caption('When a place becomes available, select a waiting student below.')
        selected = st.selectbox('Waiting student', waiting, format_func=lambda w: f'{w[1]} - {w[2]}')
        if st.button('Assign Waiting Student'):
            try:
                st.session_state['message'] = db.allocate(selected[0], selected[4])
                st.rerun()
            except ValueError as error:
                st.error(str(error))

elif page == 'Trial Lessons':
    st.header('Trial Lesson Management')
    choices = db.trial_candidates()
    if not choices:
        st.info('No group-assigned students are waiting for a trial lesson.')
    else:
        options = {f'{s[0]} - {s[1]}': s for s in choices}
        student = options[st.selectbox('Select Student', list(options))]
        st.write('Assigned group:', student[2])
        with st.form('trial_form'):
            date = st.date_input('Trial Date')
            time = st.time_input('Trial Time')
            attendance = st.selectbox('Attendance', ['Scheduled', 'Attended', 'Not Attended'])
            decision = st.selectbox('Student Decision',
                                    ['Pending', 'Wants to Enroll', 'Does Not Want to Enroll'])
            notes = st.text_area('Notes (optional)')
            if st.form_submit_button('Save Trial Lesson'):
                try:
                    db.save_trial(student[0], str(date), str(time), attendance, decision, notes)
                    st.success('Trial lesson saved successfully.')
                except ValueError as error:
                    st.error(str(error))
    st.subheader('Trial Lesson Records')
    st.dataframe(pd.DataFrame(db.trial_records(), columns=[
        'Student', 'Date', 'Time', 'Attendance', 'Decision', 'Status'
    ]), hide_index=True, use_container_width=True)

elif page == 'Payments':
    st.header('Payment and Enrollment')
    candidates = db.payment_candidates()
    if not candidates:
        st.info('No students are currently ready for payment.')
    else:
        options = {f'{s[0]} - {s[1]}': s for s in candidates}
        student = options[st.selectbox('Select Student', list(options))]
        st.write('Assigned group:', student[2])
        with st.form('payment_form'):
            st.caption('Enter the agreed course fee in UZS (not a fixed IELTS Zone price).')
            amount_due = st.number_input('Course Fee (UZS)', min_value=1, value=1000000, step=100000)
            amount_paid = st.number_input('Amount Paid (UZS)', min_value=0, value=0, step=100000)
            method = st.selectbox('Payment Method', ['Cash', 'Card', 'Bank Transfer'])
            date = st.date_input('Payment Date')
            if st.form_submit_button('Confirm Payment and Enroll'):
                try:
                    db.save_payment(student[0], amount_due, amount_paid, method, str(date))
                    st.success('Full payment recorded. Student enrolled successfully!')
                except ValueError as error:
                    st.error(str(error))
    st.subheader('Payment and Enrollment Records')
    st.dataframe(pd.DataFrame(db.payment_records(), columns=[
        'Student', 'Course Fee (UZS)', 'Amount Paid (UZS)',
        'Method', 'Date', 'Status'
    ]), hide_index=True, use_container_width=True)
